"""The narration the LLM writes for a chapter, pasted into
chapters/chapter_N/narration.json, and everything remanga checks about it.

Its shape is prompts/narration.md's Reply section: one entry per PANEL of the
chapter, in reading order, each with the narration `text` read while that panel
is on screen; a marked panel that isn't story (a credits box, a title) is
skipped with a reason instead. The reply's second section, `memory`, is the
story so far after this chapter, which the next chapter's PDF reads straight
from this file.

A reply that doesn't check out stops the video before anything is
synthesized, and gets a fix request (pdf/chapter_N/fix_request.md) to paste
back into the same LLM conversation."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from remanga.chapters import chapter_sort_key
from remanga.json_io import has_real_json_content, json_blocks_from_reply
from remanga.paths import PROMPTS_DIR, get_narration_path, get_pages_dir, get_panels_dir, get_pdf_dir

PROMPT_PATH = PROMPTS_DIR / "narration.md"
FIX_REQUEST_NAME = "fix_request.md"
SKIP_REASONS = ("credits", "ad", "blank", "duplicate", "title")
PANEL_KEYS = ("panel", "skip", "text")
# A panel told in fewer words than this is usually a caption, not the panel
# and everything said in it.
MIN_WORDS_PER_PANEL = 5
PAGE_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
PANEL_IMAGE_EXTS = PAGE_IMAGE_EXTS

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
class StoryPanel:
    panel: Path
    text: str

    @property
    def panel_id(self) -> str:
        return self.panel.stem


def page_files(project: str, chapter: str) -> list[Path]:
    """The chapter's downloaded pages, in order."""
    pages_dir = get_pages_dir(project, chapter)
    if not pages_dir.exists():
        return []
    return sorted(p for p in pages_dir.iterdir() if p.is_file() and p.suffix.lower() in PAGE_IMAGE_EXTS)


def panel_files(project: str, chapter: str) -> list[Path]:
    """The panels cut from this chapter's pages, in reading order - their
    names sort into it (cropper/naming.py)."""
    panels_dir = get_panels_dir(project, chapter, create=False)
    if not panels_dir.exists():
        return []
    return sorted(p for p in panels_dir.iterdir() if p.is_file() and p.suffix.lower() in PANEL_IMAGE_EXTS)


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


def check_reply(doc: Any, panel_stems: list[str], chapter: str) -> Check:
    check = Check()
    if not isinstance(doc, dict) or not isinstance(doc.get("panels"), list):
        check.errors.append('the reply is not a JSON object with a "panels" list')
        return check
    if "chapter" in doc and str(doc["chapter"]).strip().lstrip("0") != str(chapter).strip().lstrip("0"):
        check.warnings.append(f"the reply says chapter {doc['chapter']!r}, but it is chapter {chapter}'s file")
    check.warnings.extend(f"the LLM reported: {problem}" for problem in doc.get("problems") or [])
    if "memory" in doc and not isinstance(doc["memory"], dict):
        check.errors.append('"memory" must be a JSON object, the story so far')

    known, seen, told = set(panel_stems), [], 0
    for entry in doc["panels"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("panel"), str):
            check.errors.append(f"an entry in panels has no panel ID: {json.dumps(entry)[:80]}")
            continue
        stem = entry["panel"]
        if stem not in known:
            check.errors.append(f"panel {stem} is not one of this chapter's panels")
            continue
        if stem in seen:
            check.errors.append(f"panel {stem} appears more than once")
            continue
        seen.append(stem)
        skip, text = entry.get("skip"), entry.get("text")
        if skip:
            if skip not in SKIP_REASONS:
                check.errors.append(f"{stem}: skip must be one of {', '.join(SKIP_REASONS)} (got {skip!r})")
            if text:
                check.errors.append(f"{stem}: a skipped panel has no narration - its text must be empty")
            continue
        if not isinstance(text, str) or not text.strip():
            check.errors.append(f"{stem}: needs its narration in text, or a skip reason")
            continue
        told += 1
        if len(text.split()) < MIN_WORDS_PER_PANEL:
            check.warnings.append(f"{stem}: {len(text.split())} words - is everything in the panel told, with all "
                                  f"of its dialogue")
        check.warnings.extend(_style_warnings(stem, text))
        unknown = sorted(set(entry) - set(PANEL_KEYS))
        if unknown:
            check.warnings.append(f"{stem}: ignored unknown key(s) {', '.join(unknown)}")

    missing = [stem for stem in panel_stems if stem not in seen]
    if missing:
        check.errors.append(f"panel(s) missing from panels: {', '.join(missing)}")
    if not missing and not told:
        check.errors.append("every panel is skipped - there is nothing to narrate")
    return check


def fix_request_text(chapter: str, errors: list[str]) -> str:
    """What to paste back into the same LLM conversation."""
    return "\n".join([
        f"The narration for chapter {chapter} didn't pass the checks. Fix only the problems below, checked "
        f"against the panels, and reply again in full - the one JSON block with both sections, narration (every "
        f"panel) and memory - not only what changed.",
        "",
        *[f"- {error}" for error in errors],
    ]) + "\n"


def read_reply(path: Path) -> tuple[Any, dict[str, Any] | None]:
    """A pasted reply's narration document and its memory. The reply is one
    JSON block with two sections, `{"narration": {...}, "memory": {...}}`.
    Also read: a reply with `panels` and `memory` side by side, or two separate
    blocks, the narration then the memory."""
    blocks = json_blocks_from_reply(path.read_text(encoding="utf-8"))
    first = blocks[0]
    if isinstance(first, dict) and isinstance(first.get("narration"), dict):
        doc, memory = first["narration"], first.get("memory")
    else:
        doc = next((b for b in blocks if isinstance(b, dict) and "panels" in b), first)
        memory = doc.get("memory") if isinstance(doc, dict) else None
        if not isinstance(memory, dict):
            memory = next((b for b in blocks if isinstance(b, dict) and b is not doc and "panels" not in b), None)
    return doc, memory if isinstance(memory, dict) and memory else None


def load_narration(project: str, chapter: str) -> tuple[list[StoryPanel], Check]:
    """The chapter's panels with their narration, in reading order, and the
    check's warnings. Raises NarrationError - after writing the fix request -
    when the narration is missing or doesn't check out."""
    path = get_narration_path(project, chapter)
    if not has_real_json_content(path):
        raise NarrationError(f"Chapter {chapter} has no narration yet - paste the LLM's reply into {path}")
    panels = panel_files(project, chapter)
    if not panels:
        raise NarrationError(f"Chapter {chapter} has no panels yet - mark them in the Panel Marker and cut them "
                             f"first.")

    fix_path = get_pdf_dir(project, chapter) / FIX_REQUEST_NAME
    try:
        doc, memory = read_reply(path)
        check = check_reply(doc, [p.stem for p in panels], chapter)
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

    entries = {entry["panel"]: entry for entry in doc["panels"]}
    return [StoryPanel(panel, entries[panel.stem]["text"].strip()) for panel in panels
            if not entries[panel.stem].get("skip")], check


def narration_document(chapter: str, entries: Sequence[tuple[str, str]],
                       memory: dict[str, Any] | None = None) -> dict[str, Any]:
    """The narration.json document for a chapter, from (panel_id, text) pairs -
    the same shape the LLM is asked for (prompts/narration.md), so a file
    written by hand in the Narration Writer and one pasted from a reply are
    the same file. An empty text is a panel with nothing to say, kept as a
    skip so the checks do not call it missing."""
    panels = [{"panel": panel_id, "text": text.strip()} if text and text.strip()
              else {"panel": panel_id, "skip": "blank", "text": ""}
              for panel_id, text in entries]
    document: dict[str, Any] = {"narration": {"chapter": str(chapter), "problems": [], "panels": panels}}
    if memory:
        document["memory"] = memory
    return document


def written_panels(path: Path) -> tuple[dict[str, str], dict[str, Any] | None]:
    """What a narration.json already holds: {panel id: text} and its memory
    section. Empty when there is nothing readable there yet - a half-written
    file must not stop the writer from opening."""
    if not has_real_json_content(path):
        return {}, None
    try:
        doc, memory = read_reply(path)
        panels = doc.get("panels") if isinstance(doc, dict) else None
        return {str(e.get("panel")): str(e.get("text") or "") for e in panels or []
                if isinstance(e, dict) and e.get("panel")}, memory
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return {}, None


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
