"""narration.json: its shape, and creating one from scratch.

The file every downstream stage reads (TTS, mix, render, verify) is written
by three different things - an LLM's copy/paste reply, the Narration Writer
web UI, and now `narration-init` - so the shape itself is defined once,
here, and built through `narration_document`. A template that didn't match
what the Writer produces would be a trap: it would look right and then
disagree about a key name three stages later.

Two ways to start a chapter's file, because they're for different
workflows:

- "template": the complete skeleton for this chapter - one entry per
  cropped panel, in panel order, each with empty text. What the Narration
  Writer creates when it opens, so you can hand-fill it in an editor, or
  hand it to an LLM as the exact structure to fill in, without either of
  them having to invent the panel list.
- "blank": a genuinely empty file. Zero bytes - not "{}", not "[]", nothing
  at all. That's the placeholder state the rest of remanga already
  understands as "not written yet" (see json_io.has_real_json_content), so
  it reserves the path without any stage mistaking it for real content.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from remanga.console import console, display_path
from remanga.json_io import has_real_json_content, read_json, write_json
from remanga.narration.normalize import normalize_text
from remanga.paths import get_chapter_dir

# What counts as a panel image when reading a chapter's panels/ folder.
PANEL_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

TEMPLATE = "template"
BLANK = "blank"


@dataclass(frozen=True)
class NarrationFileMode:
    """One way to create narration.json, described where it's implemented so
    the CLI's --help, the wizard's menu and the code can't disagree."""

    name: str
    label: str
    summary: str
    detail: str


NARRATION_FILE_MODES: Tuple[NarrationFileMode, ...] = (
    NarrationFileMode(
        TEMPLATE, "Full template",
        "one entry per cropped panel, every text empty",
        "the same skeleton the Narration Writer creates - fill it in by hand or hand it to an LLM",
    ),
    NarrationFileMode(
        BLANK, "Completely empty",
        "a zero-byte file - not even {}",
        "reserves the path; every stage reads it as 'not written yet'",
    ),
)

NARRATION_FILE_MODE_NAMES = tuple(mode.name for mode in NARRATION_FILE_MODES)
NARRATION_FILE_MODE_BY_NAME = {mode.name: mode for mode in NARRATION_FILE_MODES}


def narration_path(project_name: str, chapter_num: str) -> Path:
    return get_chapter_dir(project_name, chapter_num) / "narration.json"


def panel_ids(project_name: str, chapter_num: str) -> List[str]:
    """Every cropped panel's id for this chapter, in order.

    The id is the panel file's stem, because that's what render.py keys off
    when it pairs narration with images - deriving it here from the same
    files means a generated template can't produce a panel_id that doesn't
    match a panel."""
    panels_dir = get_chapter_dir(project_name, chapter_num) / "panels"
    if not panels_dir.is_dir():
        return []
    return sorted(p.stem for p in panels_dir.iterdir() if p.suffix.lower() in PANEL_IMAGE_EXTS)


def narration_document(chapter_num: str, entries: Sequence[Tuple[str, str]]) -> Dict[str, Any]:
    """The narration.json document for a chapter, from (panel_id, text)
    pairs. The one place this structure is spelled out."""
    narration = [{"panel_id": panel_id, "text": text or ""} for panel_id, text in entries]
    return {
        "chapter": str(chapter_num),
        "total_panels": len(narration),
        "narration": narration,
    }


def create_narration_file(
    project_name: str, chapter_num: str, mode: str = TEMPLATE, force: bool = False,
) -> Path:
    """Creates (or replaces) this chapter's narration.json. Returns its path.

    Refuses to overwrite a file that already holds real content unless
    `force` - losing a written narration script to a mistyped command is
    exactly the kind of thing that isn't recoverable from anywhere else."""
    if mode not in NARRATION_FILE_MODE_BY_NAME:
        raise ValueError(
            f"Unknown narration file mode {mode!r} - expected one of "
            f"{', '.join(NARRATION_FILE_MODE_NAMES)}."
        )

    path = narration_path(project_name, chapter_num)
    if has_real_json_content(path) and not force:
        raise FileExistsError(
            f"{path} already has narration in it. Pass --force to replace it "
            f"(the wizard asks), or edit it with `write` instead."
        )

    path.parent.mkdir(parents=True, exist_ok=True)

    if mode == BLANK:
        path.write_text("", encoding="utf-8")
        console.print("[bold green]✓ Empty narration.json created[/] [dim](0 bytes)[/]")
        console.print(f"  {display_path(path)}")
        return path

    ids = panel_ids(project_name, chapter_num)
    if not ids:
        raise FileNotFoundError(
            f"No cropped panels found for chapter {chapter_num} - a template needs the panel "
            f"list, so run `crop` for this chapter first (or create a blank file with "
            f"--mode blank)."
        )

    write_json(path, narration_document(chapter_num, [(panel_id, "") for panel_id in ids]))
    console.print(
        f"[bold green]✓ narration.json template created[/] "
        f"[dim]({len(ids)} panel(s), every text empty)[/]"
    )
    console.print(f"  {display_path(path)}")
    return path


@dataclass(frozen=True)
class PanelChange:
    """One panel's text before and after normalization, plus which rules
    fired - so a preview can show what a change actually was, not just that
    something changed."""

    panel_id: str
    before: str
    after: str
    rules: List[str]


def normalize_narration(project_name: str, chapter_num: str) -> Tuple[Dict[str, Any], List[PanelChange]]:
    """Reads this chapter's narration.json and returns (normalized document,
    the panels that changed). Writes nothing - the caller previews, confirms,
    and only then saves, because narration text is hand-written or
    LLM-generated and not regenerable from anything on disk.

    Raises if there's no narration to normalize yet."""
    path = narration_path(project_name, chapter_num)
    if not has_real_json_content(path):
        raise FileNotFoundError(
            f"No narration to normalize at {path} - write it first (`write`, the LLM flow, or "
            f"`narration-init`)."
        )

    document = read_json(path)
    changes: List[PanelChange] = []
    for entry in document.get("narration", []):
        before = entry.get("text", "") or ""
        after, rules = normalize_text(before)
        if after != before:
            changes.append(PanelChange(entry.get("panel_id", "?"), before, after, rules))
            entry["text"] = after
    return document, changes


def save_narration(project_name: str, chapter_num: str, document: Dict[str, Any]) -> Path:
    """Writes narration.json back. Atomic, like every JSON write here."""
    path = narration_path(project_name, chapter_num)
    write_json(path, document)
    return path
