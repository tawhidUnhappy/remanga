"""The narration the LLM writes for a chapter, pasted into
chapters/chapter_N/narration.json, and everything remanga checks about it.

Its shape is prompts/narration.md's <output_format>: one entry per page of the
chapter, in order - a story page lists its panels (one short note each, in
reading order) and its narration `text`, which tells every one of those
panels; a page that isn't story (credits, an ad, a blank page) is skipped with
a reason. The reply's second section, `memory`, is the story so far after this
chapter, which the next chapter's PDF reads straight from this file.

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
from remanga.json_io import has_real_json_content, json_blocks_from_reply
from remanga.paths import PROMPTS_DIR, get_narration_path, get_pages_dir, get_pdf_dir

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
        f"against the pages, and reply again in full - the one JSON block with both sections, narration (every "
        f"page) and memory - not only what changed.",
        "",
        *[f"- {error}" for error in errors],
    ]) + "\n"


def read_reply(path: Path) -> tuple[Any, dict[str, Any] | None]:
    """A pasted reply's narration document and its memory. The reply is one
    JSON block with two sections, `{"narration": {...}, "memory": {...}}`.
    Also read: a reply with `pages` and `memory` side by side, or two separate
    blocks, the narration then the memory."""
    blocks = json_blocks_from_reply(path.read_text(encoding="utf-8"))
    first = blocks[0]
    if isinstance(first, dict) and isinstance(first.get("narration"), dict):
        doc, memory = first["narration"], first.get("memory")
    else:
        doc = next((b for b in blocks if isinstance(b, dict) and "pages" in b), first)
        memory = doc.get("memory") if isinstance(doc, dict) else None
        if not isinstance(memory, dict):
            memory = next((b for b in blocks if isinstance(b, dict) and b is not doc and "pages" not in b), None)
    return doc, memory if isinstance(memory, dict) and memory else None


def load_narration(project: str, chapter: str) -> tuple[list[StoryPage], Check]:
    """The chapter's story pages with their narration, in page order, and the
    check's warnings. Raises NarrationError - after writing the fix request -
    when the narration is missing or doesn't check out."""
    path = get_narration_path(project, chapter)
    if not has_real_json_content(path):
        raise NarrationError(f"Chapter {chapter} has no narration yet - paste the LLM's reply into {path}")
    pages = page_files(project, chapter)
    if not pages:
        raise NarrationError(f"Chapter {chapter} has no downloaded pages - download it first.")

    fix_path = get_pdf_dir(project, chapter) / FIX_REQUEST_NAME
    try:
        doc, memory = read_reply(path)
        check = check_reply(doc, [p.stem for p in pages], chapter)
        if not memory:
            check.warnings.append("the reply has no memory section - the next chapter's PDF will carry the story so "
                                  "far from an earlier chapter instead")
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
    return [StoryPage(page, entries[page.stem]["text"].strip()) for page in pages
            if entries[page.stem]["story"]], check


def story_so_far(project: str, chapter: str) -> tuple[dict[str, Any] | None, str | None]:
    """The memory section of the nearest earlier chapter whose pasted narration
    has one, and which chapter that is - read straight from its narration.json,
    so the next chapter's PDF carries it without any other step. (None, None)
    when no earlier chapter has one."""
    from remanga.chapters import discover_chapters

    earlier = [c for c in discover_chapters(project) if chapter_sort_key(c) < chapter_sort_key(str(chapter))]
    for previous in reversed(earlier):
        path = get_narration_path(project, previous)
        if not has_real_json_content(path):
            continue
        try:
            _, memory = read_reply(path)
        except (json.JSONDecodeError, OSError, IndexError):
            continue
        if memory:
            return memory, previous
    return None, None
