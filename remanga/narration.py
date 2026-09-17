"""The narration the LLM writes for a chapter, pasted into
chapters/chapter_N/narration.json, and everything remanga checks about it.

Its shape is prompts/narration.md's <output_format>: one entry per page of the
chapter, in order - a story page lists its panels (one short note each, in
reading order) and its narration `text`, which tells every one of those
panels; a page that isn't story (credits, an ad, a blank page) is skipped with
a reason - plus `memory`, the story so far, carried into the next chapter's
PDF.

A reply that doesn't check out stops the video before anything is
synthesized, and gets a fix request (pdf/chapter_N/fix_request.md) to paste
back into the same LLM conversation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from remanga.chapters import chapter_sort_key
from remanga.json_io import has_real_json_content, json_from_reply, read_json_or, write_json
from remanga.paths import PROMPTS_DIR, get_memory_path, get_narration_path, get_pages_dir, get_pdf_dir

PROMPT_PATH = PROMPTS_DIR / "narration.md"
FIX_REQUEST_NAME = "fix_request.md"
SKIP_REASONS = ("credits", "ad", "blank", "duplicate")
PAGE_KEYS = ("page", "story", "skip", "panels", "text")
# Fewer words than this per listed panel usually means panels were summed up
# rather than each told.
MIN_WORDS_PER_PANEL = 12
PAGE_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

_CONTRACTION = re.compile(r"\b\w+(?:n't|'re|'ve|'ll|'d|'m)\b|\b(?:it|that|there|what|he|she|who|here)'s\b",
                          re.IGNORECASE)


class NarrationError(ValueError):
    """The narration can't be used as it is; the message says why and where
    the fix request was written."""


@dataclass
class Check:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StoryPage:
    page: Path
    text: str

    @property
    def page_id(self) -> str:
        return self.page.stem


def page_files(project: str, chapter: str) -> list[Path]:
    """The chapter's downloaded pages, in order."""
    pages_dir = get_pages_dir(project, chapter)
    if not pages_dir.exists():
        return []
    return sorted(p for p in pages_dir.iterdir() if p.is_file() and p.suffix.lower() in PAGE_IMAGE_EXTS)


def _style_warnings(stem: str, text: str) -> list[str]:
    """prompts/narration.md's voice rules that a program can see."""
    found = []
    if re.search(r"[\"“”]", text):
        found.append("quotation marks")
    if "?" in text or "!" in text:
        found.append("a question or exclamation mark")
    if "..." in text or "…" in text:
        found.append("an ellipsis")
    contractions = sorted({m.group(0) for m in _CONTRACTION.finditer(text)})
    if contractions:
        found.append(f"contractions ({', '.join(contractions[:4])})")
    return [f"{stem}: the narration uses {', '.join(found)} - the voice rules forbid them"] if found else []


def check_reply(doc: Any, page_stems: list[str], chapter: str) -> Check:
    check = Check()
    if not isinstance(doc, dict) or not isinstance(doc.get("pages"), list):
        check.errors.append('the reply is not a JSON object with a "pages" list')
        return check
    if "chapter" in doc and str(doc["chapter"]).strip().lstrip("0") != str(chapter).strip().lstrip("0"):
        check.warnings.append(f"the reply says chapter {doc['chapter']!r}, but it is chapter {chapter}'s file")
    check.warnings.extend(f"the LLM reported: {problem}" for problem in doc.get("problems") or [])
    if "memory" in doc and not isinstance(doc["memory"], dict):
        check.errors.append('"memory" must be a JSON object, the story so far')

    known, seen, story_pages = set(page_stems), [], 0
    for entry in doc["pages"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("page"), str):
            check.errors.append(f"an entry in pages has no page ID: {json.dumps(entry)[:80]}")
            continue
        stem = entry["page"]
        if stem not in known:
            check.errors.append(f"page {stem} is not one of this chapter's pages")
            continue
        if stem in seen:
            check.errors.append(f"page {stem} appears more than once")
            continue
        seen.append(stem)
        story, panels, text = entry.get("story"), entry.get("panels"), entry.get("text")
        if not isinstance(story, bool):
            check.errors.append(f'{stem}: "story" must be true or false')
            continue
        if not story:
            if entry.get("skip") not in SKIP_REASONS:
                check.errors.append(f"{stem}: a page that is not part of the story needs a skip of "
                                    f"{', '.join(SKIP_REASONS)} (got {entry.get('skip')!r})")
            if text:
                check.errors.append(f"{stem}: a skipped page has no narration - its text must be empty")
            continue
        story_pages += 1
        if not isinstance(panels, list) or not panels or not all(isinstance(p, str) and p.strip() for p in panels):
            check.errors.append(f'{stem}: "panels" must list every panel on the page, one short note each, in '
                                f"reading order")
            panels = None
        if not isinstance(text, str) or not text.strip():
            check.errors.append(f"{stem}: a story page needs its narration in text")
            continue
        if panels and len(text.split()) < MIN_WORDS_PER_PANEL * len(panels):
            check.warnings.append(f"{stem}: {len(text.split())} words for {len(panels)} panels - is every panel "
                                  f"told, with all of its dialogue")
        check.warnings.extend(_style_warnings(stem, text))
        unknown = sorted(set(entry) - set(PAGE_KEYS))
        if unknown:
            check.warnings.append(f"{stem}: ignored unknown key(s) {', '.join(unknown)}")

    missing = [stem for stem in page_stems if stem not in seen]
    if missing:
        check.errors.append(f"page(s) missing from pages: {', '.join(missing)}")
    if not missing and not story_pages:
        check.errors.append("every page is marked as not part of the story - there is nothing to narrate")
    return check


def fix_request_text(chapter: str, errors: list[str]) -> str:
    """What to paste back into the same LLM conversation."""
    return "\n".join([
        f"The narration for chapter {chapter} didn't pass the checks. Fix only the problems below, checked "
        f"against the pages, and reply again with the complete JSON - every page and the memory, not only what "
        f"changed.",
        "",
        *[f"- {error}" for error in errors],
    ]) + "\n"


def load_narration(project: str, chapter: str) -> tuple[list[StoryPage], Check]:
    """The chapter's story pages with their narration, in page order, and the
    check's warnings. Raises NarrationError - after writing the fix request -
    when the narration is missing or doesn't check out. On success, the
    reply's memory is saved to memory.json (see save_memory)."""
    path = get_narration_path(project, chapter)
    if not has_real_json_content(path):
        raise NarrationError(f"Chapter {chapter} has no narration yet - paste the LLM's reply into {path}")
    pages = page_files(project, chapter)
    if not pages:
        raise NarrationError(f"Chapter {chapter} has no downloaded pages - download it first.")

    fix_path = get_pdf_dir(project, chapter) / FIX_REQUEST_NAME
    try:
        doc = json_from_reply(path.read_text(encoding="utf-8"))
        check = check_reply(doc, [p.stem for p in pages], chapter)
    except json.JSONDecodeError as error:
        doc, check = None, Check(errors=[f"the reply is not valid JSON ({error.msg} at line {error.lineno}, "
                                         f"column {error.colno})"])
    if check.errors:
        fix_path.write_text(fix_request_text(chapter, check.errors), encoding="utf-8")
        raise NarrationError(
            f"Chapter {chapter}'s narration has {len(check.errors)} problem(s):\n"
            + "\n".join(f"  - {error}" for error in check.errors)
            + f"\nPaste this into the same LLM chat and save its new reply over narration.json: {fix_path}"
        )
    fix_path.unlink(missing_ok=True)

    entries = {entry["page"]: entry for entry in doc["pages"]}
    save_memory(project, chapter, doc.get("memory"))
    return [StoryPage(page, entries[page.stem]["text"].strip()) for page in pages
            if entries[page.stem]["story"]], check


def save_memory(project: str, chapter: str, memory: Any) -> None:
    """The story so far from a chapter's reply into memory.json - unless
    memory.json already holds a later chapter's, which a re-run of an earlier
    chapter must not roll back."""
    if not isinstance(memory, dict) or not memory:
        return
    path = get_memory_path(project)
    current = read_json_or(path, {}) if has_real_json_content(path) else {}
    latest = str(current.get("last_chapter_processed", "")) if isinstance(current, dict) else ""
    if latest and chapter_sort_key(latest) > chapter_sort_key(str(chapter)):
        return
    write_json(path, {**memory, "last_chapter_processed": str(chapter)})


def story_so_far(project: str) -> dict[str, Any] | None:
    path = get_memory_path(project)
    memory = read_json_or(path, None) if has_real_json_content(path) else None
    return memory if isinstance(memory, dict) and memory else None
