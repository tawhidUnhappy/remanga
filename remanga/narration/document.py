"""The narration the LLM writes for a chapter, pasted into
chapters/chapter_N/narration.json, and everything remanga checks about it.

Its shape is prompts/narration.md's Reply section: every PANEL of the chapter,
in reading order, keyed by its id, with the narration read while that panel is
on screen; a marked panel that isn't story (a credits box, a title) is skipped
with a reason instead. (An older reply lists `{"panel", "text"}` entries; both
read the same.) The reply's second section, `memory`, is what the chapter
changed in the story - the next chapter's PDF folds every earlier chapter's
into the story so far (story.py).

A reply that doesn't check out stops the video before anything is
synthesized, and gets a fix request (pdf/chapter_N/fix_request.md) to paste
back into the same LLM conversation. Its answer - like the answer to a review
(prompts/narration_review.md) - is a patch holding only the panels it changes,
saved over narration.json like a reply and merged here into the narration it
fixes (kept as narration_base.json when the patch was asked for)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from remanga.chapters import chapter_sort_key
from remanga.json_io import has_real_json_content, json_blocks_from_reply
from remanga.narration.check import Check, NarrationError, check_reply, fix_request_text
from remanga.narration.files import PANEL_IMAGE_EXTS, panel_files
from remanga.narration.story import ENTRIES, Story, add_chapter, memory_problems
from remanga.paths import PROMPTS_DIR, get_narration_path, get_pdf_dir

PROMPT_PATH = PROMPTS_DIR / "narration.md"
FIX_REQUEST_NAME = "fix_request.md"
# The narration a patch is merged into, and the last patch merged.
BASE_NAME, PATCH_NAME = "narration_base.json", "narration_patch.json"

_SKIP_VALUE = re.compile(r"\s*skip\s+(\w+)\s*\.?\s*", re.IGNORECASE)


@dataclass(frozen=True)
class StoryPanel:
    panel: Path
    text: str

    @property
    def panel_id(self) -> str:
        return self.panel.stem


def panel_entries(panels: Any) -> Any:
    """A reply's panels as the entries the checks read - `{"panel", "text"}`
    or `{"panel", "skip", "text": ""}`, in order - from the object keyed by
    panel id the reply skeleton asks for ("skip REASON" for a skipped panel),
    or the list an older reply holds. A panel id the object held twice comes
    back twice, so the checks can say so."""
    if not isinstance(panels, dict):
        return panels
    pairs = [*panels.items(), *((panel, panels[panel]) for panel in getattr(panels, "duplicates", ()))]
    entries = []
    for panel, value in pairs:
        skip = _SKIP_VALUE.fullmatch(value) if isinstance(value, str) else None
        entries.append({"panel": panel, **value} if isinstance(value, dict)
                       else {"panel": panel, "skip": skip.group(1).lower(), "text": ""} if skip
                       else {"panel": panel, "text": value})
    return entries


def read_reply(path: Path) -> tuple[Any, dict[str, Any] | None]:
    """A pasted reply's narration document, its panels as entries in order
    (panel_entries), and its memory. The reply is one JSON block with two
    sections, `{"narration": {...}, "memory": {...}}`. Also read: a reply with
    `panels` and `memory` side by side, two separate blocks (the narration
    then the memory), and a patch, `{"patch": {...}}`, merged first into the
    narration it fixes (merge_patch)."""
    blocks = json_blocks_from_reply(path.read_text(encoding="utf-8"))
    first = blocks[0]
    if isinstance(first, dict) and isinstance(first.get("patch"), dict):
        return merge_patch(path, first["patch"])
    if isinstance(first, dict) and isinstance(first.get("narration"), dict):
        doc, memory = first["narration"], first.get("memory")
    else:
        doc = next((b for b in blocks if isinstance(b, dict) and "panels" in b), first)
        memory = doc.get("memory") if isinstance(doc, dict) else None
        if not isinstance(memory, dict):
            memory = next((b for b in blocks if isinstance(b, dict) and b is not doc and "panels" not in b), None)
    if isinstance(doc, dict):
        doc = {**doc, "panels": panel_entries(doc.get("panels"))}
    return doc, memory if isinstance(memory, dict) and memory else None


def keep_base(path: Path) -> None:
    """Keeps the narration now in `path` as the one the next patch is merged
    into - done when a fix request or a review is about to ask for one."""
    base, data = path.with_name(BASE_NAME), path.read_bytes()
    if not base.exists() or base.read_bytes() != data:
        base.write_bytes(data)


def merge_patch(path: Path, patch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """A patch merged into the narration it fixes (BASE_NAME beside `path`):
    its panels replace those with the same id, its memory sections replace
    the base's (a name in characters, places or terms is added or replaced
    on its own). The result is written over `path`, whole, so from then on it
    reads as an ordinary reply; the patch is kept as PATCH_NAME."""
    base_path = path.with_name(BASE_NAME)
    if path == base_path or not has_real_json_content(base_path):
        raise NarrationError(f"{path.name} holds a fix for one part of the narration (a patch), but the narration "
                             f"it fixes is not kept ({base_path.name}) - paste the LLM's whole reply instead")
    base, memory = read_reply(base_path)
    entries: dict[str, dict[str, Any]] = {}
    for entry in [*(base.get("panels") or []), *(panel_entries(patch.get("panels") or {}) or [])]:
        if isinstance(entry, dict) and isinstance(entry.get("panel"), str):
            entries[entry["panel"]] = entry
    order = [p.stem for p in sorted((path.parent / "panels").glob("*")) if p.suffix.lower() in PANEL_IMAGE_EXTS]
    panels = [entries[p] for p in order if p in entries] + [e for p, e in entries.items() if p not in order]
    if isinstance(patch.get("memory"), dict):
        memory = dict(memory or {})
        for key, value in patch["memory"].items():
            both = key in ENTRIES and isinstance(value, dict) and isinstance(memory.get(key), dict)
            memory[key] = {**memory[key], **value} if both else value
    doc = {"chapter": str(patch.get("chapter") or base.get("chapter") or ""),
           "problems": list(patch.get("problems") or []), "panels": panels}
    path.with_name(PATCH_NAME).write_bytes(path.read_bytes())
    partial = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    partial.write_text(json.dumps({"narration": doc, **({"memory": memory} if memory else {})}, indent=2,
                                  ensure_ascii=False) + "\n", encoding="utf-8")
    partial.replace(path)
    return doc, memory or None


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
    patch = False
    try:
        doc, memory = read_reply(path)
        check = check_reply(doc, [p.stem for p in panels], chapter)
        if memory:
            errors, warnings = memory_problems(memory)
            check.errors += errors
            check.warnings += warnings
        else:
            check.warnings.append("the reply has no memory section - the next chapter's PDF will carry the story so "
                                  "far without this chapter")
        # A reply that reads can be fixed with a patch; one that is not JSON
        # has to come again whole.
        patch = isinstance(doc, dict) and isinstance(doc.get("panels"), list)
    except json.JSONDecodeError as error:
        doc, check = None, Check(errors=[f"the reply is not valid JSON ({error.msg} at line {error.lineno}, "
                                         f"column {error.colno})"])
    if check.errors:
        if patch:
            keep_base(path)
        fix_path.write_text(fix_request_text(chapter, check.errors, patch), encoding="utf-8")
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


def story_so_far(project: str, chapter: str, through: bool = False) -> tuple[Story | None, str | None]:
    """The story as it stands before `chapter` (after it, with `through`):
    the memory of every earlier chapter's pasted narration folded in reading
    order (story.py), read straight from their narration.json files, so the
    next chapter's PDF carries it without any other step - and the last
    chapter folded in. (None, None) when none of them has a memory."""
    from remanga.chapters import discover_chapters

    end, story = chapter_sort_key(str(chapter)), None
    for earlier in discover_chapters(project):
        key = chapter_sort_key(earlier)
        if key > end or (key == end and not through):
            continue
        path = get_narration_path(project, earlier)
        if not has_real_json_content(path):
            continue
        try:
            _, memory = read_reply(path)
        except (json.JSONDecodeError, OSError, IndexError, ValueError):
            continue
        if memory and not memory_problems(memory)[0]:
            story = add_chapter(story, earlier, memory)
    return story, story.through if story else None
