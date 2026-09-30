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
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from remanga.chapters import chapter_sort_key
from remanga.json_io import has_real_json_content, json_blocks_from_reply
from remanga.narration.check import Check, NarrationError, check_reply, fix_request_text
from remanga.narration.files import panel_files
from remanga.paths import PROMPTS_DIR, get_narration_path, get_pdf_dir

PROMPT_PATH = PROMPTS_DIR / "narration.md"
FIX_REQUEST_NAME = "fix_request.md"


@dataclass(frozen=True)
class StoryPanel:
    panel: Path
    text: str

    @property
    def panel_id(self) -> str:
        return self.panel.stem


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
