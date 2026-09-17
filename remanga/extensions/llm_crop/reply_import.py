"""Gemini's crops into crops.json: reading the reply pasted into
llm_crops.json, checking it (reply_check), converting it, and writing a fix
request to paste back when it doesn't check out.

The reply's boxes are measured on the square grid images, so each one is
converted to the page's own 0-1000 box (grid.PageExtent.to_page_box) before
it goes anywhere near crops.json. crops.json stays the one file the cropper,
the marker, `status` and `restart` read: each Gemini crop becomes a
structured crop (remanga.cropper.structured) with `src: "llm"`."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.extensions.llm_crop.bundles import ChapterPage, chapter_pages
from remanga.extensions.llm_crop.config import LLMCropConfig
from remanga.extensions.llm_crop.grid import PageExtent, oriented_size, page_extent
from remanga.extensions.llm_crop.paths import get_llm_crop_dir, get_llm_crops_path
from remanga.extensions.llm_crop.reply_check import BOX_KEYS, ReplyCheck, box_bounds, check_reply
from remanga.extensions.llm_crop.text_inventory import text_outside_from_inventory
from remanga.json_io import has_real_json_content, read_json_or, write_json
from remanga.paths import get_chapter_dir, load_project_metadata

LLM_SRC = "llm"
FIX_REQUEST_NAME = "fix_request.md"
# How many problems are printed before "... and N more" - the fix request
# always carries every one of them.
_PRINT_LIMIT = 12


@dataclass
class ImportOutcome:
    """What importing a chapter's reply came to: `imported`, `empty` (nothing
    pasted yet), `invalid` (see `fix_path`) or `declined` (the chapter's own
    marks were kept)."""

    state: str
    check: ReplyCheck | None = None
    fix_path: Path | None = None


def reply_document(raw: str) -> Any:
    """The JSON document inside a pasted reply. Gemini is asked for exactly
    one fenced block and nothing else, but a paste can still bring the fence
    along, a stray sentence around it, or a byte-order mark."""
    text = raw.lstrip("﻿").strip()
    fenced = re.search(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


def to_crops_json(doc: dict[str, Any], pages: list[ChapterPage], extents: dict[str, PageExtent],
                  chapter_num: str) -> dict[str, Any]:
    """A checked reply as crops.json, every box converted to its page."""
    from remanga.webui.marks_file import DECIDED_KEY, FORMAT_KEY, MARKS_FORMAT

    entries = {entry["page"]: text_outside_from_inventory(entry)[0] for entry in doc["pages"]}
    out_pages = []
    for page in pages:
        entry, extent = entries[page.stem], extents[page.stem]
        base = {"page_index": page.index, "page_filename": page.path.name}
        if not entry["story"]:
            # A decision, not an unmarked page: a later MAGI Detect in the
            # marker must not fill it in.
            out_pages.append({**base, "is_story_page": False, "panels": [], DECIDED_KEY: True,
                              "skip_reason": entry["skip"]})
            continue
        panels = []
        for crop in sorted(entry["crops"], key=lambda c: c["order"]):
            boxes = {key: [extent.to_page_box(box) for box in crop.get(key) or []] for key in BOX_KEYS}
            rect = box_bounds([box for key in BOX_KEYS for box in boxes[key]])
            panels.append({"panel_id": crop["order"], "box_1000": [int(v) for v in rect], "src": LLM_SRC,
                           "kind": crop["kind"], **boxes})
        out_pages.append({**base, "is_story_page": True, "panels": panels, DECIDED_KEY: False})
    return {"chapter": str(chapter_num), FORMAT_KEY: MARKS_FORMAT, "source": LLM_SRC, "pages": out_pages}


def fix_request_text(chapter_num: str, errors: list[str]) -> str:
    """What to paste back into the same Gemini conversation
    (prompts/llm_crop.md <follow_ups>)."""
    return "\n".join([
        f"The pipeline checked your crops for chapter {chapter_num} and found {len(errors)} problem(s):",
        "",
        *(f"- {error}" for error in errors),
        "",
        "Fix only these, checked against the page images, and leave everything else exactly as it was. "
        "Reply with the complete JSON document for the whole chapter again, as one ```json code block "
        "with nothing before or after it.",
    ]) + "\n"


def _print_lines(lines: list[str], style: str) -> None:
    for line in lines[:_PRINT_LIMIT]:
        console.print(f"  [{style}]- {_esc(line)}[/]")
    if len(lines) > _PRINT_LIMIT:
        console.print(f"  [dim]... and {len(lines) - _PRINT_LIMIT} more[/]")


def hand_marks_in(crops_path: Path) -> bool:
    """Whether crops.json holds any panel that isn't an earlier import's -
    marks drawn, detected or moved in the Panel Marker."""
    if not has_real_json_content(crops_path):
        return False
    data = read_json_or(crops_path, {})
    return any(panel.get("src") != LLM_SRC
               for page in data.get("pages", []) for panel in page.get("panels", []))


def _summarize(chapter_num: str, crops: dict[str, Any], page_count: int, check: ReplyCheck) -> None:
    panels = [panel for page in crops["pages"] if page["is_story_page"] for panel in page["panels"]]
    skipped: dict[str, int] = {}
    for page in crops["pages"]:
        if not page["is_story_page"]:
            skipped[page["skip_reason"]] = skipped.get(page["skip_reason"], 0) + 1
    console.print(
        f"[bold green]✓ Chapter {chapter_num}: crops.json written from Gemini's reply[/] "
        f"[dim]({page_count} pages · {len(panels)} crops, "
        f"{sum(panel['kind'] == 'group' for panel in panels)} of them groups"
        + (f" · skipped {', '.join(f'{n} {reason}' for reason, n in skipped.items())}" if skipped else "")
        + ")[/]"
    )
    if check.warnings:
        console.print(f"[yellow]{len(check.warnings)} thing(s) worth a look:[/]")
        _print_lines(check.warnings, "yellow")


def import_llm_crops(llm: LLMCropConfig, cropper: CropperConfig, project_name: str, chapter_num: str, *,
                     replace_marks: bool | None = None) -> ImportOutcome:
    """Checks the chapter's pasted reply and, when it passes, writes
    crops.json (and the previews). `replace_marks` answers "replace marks
    made in the Panel Marker?" up front; None asks a real terminal, and
    keeps the marks anywhere else."""
    from remanga.cropper.crop import cropped_panels

    reply = get_llm_crops_path(project_name, chapter_num)
    if not has_real_json_content(reply):
        return ImportOutcome("empty")
    pages = chapter_pages(project_name, chapter_num)
    if not pages:
        raise FileNotFoundError(f"No downloaded pages for chapter {chapter_num} - nothing to check the reply against.")
    extents = {page.stem: page_extent(*oriented_size(page.path)) for page in pages}
    direction = load_project_metadata(project_name).get("reading_direction", "right_to_left")

    fix_path = get_llm_crop_dir(project_name, chapter_num) / FIX_REQUEST_NAME
    try:
        doc = reply_document(reply.read_text(encoding="utf-8"))
        check = check_reply(doc, pages, extents, chapter_num, direction,
                            snap_step=llm.grid_tick_step or llm.grid_line_step)
    except json.JSONDecodeError as error:
        check = ReplyCheck(errors=[f"the reply is not valid JSON ({error.msg} at line {error.lineno}, "
                                   f"column {error.colno})"])
    if check.errors:
        fix_path.write_text(fix_request_text(chapter_num, check.errors), encoding="utf-8")
        console.print(f"[bold red]✗ Chapter {chapter_num}: Gemini's reply has {len(check.errors)} problem(s)[/]")
        _print_lines(check.errors, "red")
        return ImportOutcome("invalid", check=check, fix_path=fix_path)
    fix_path.unlink(missing_ok=True)

    crops_path = get_chapter_dir(project_name, chapter_num) / "crops.json"
    if hand_marks_in(crops_path):
        if replace_marks is None:
            from remanga.tui import confirm, is_interactive

            replace_marks = is_interactive() and confirm(
                f"Chapter {chapter_num} has marks from the Panel Marker - replace them with Gemini's crops?",
                default=False, note="crops.json is rewritten from llm_crops.json; the marks are not kept anywhere",
            ) is True
        if not replace_marks:
            console.print(f"[yellow]Kept chapter {chapter_num}'s Panel Marker marks[/] "
                          f"[dim](pass --force to replace them with Gemini's crops)[/]")
            return ImportOutcome("declined", check=check)

    crops = to_crops_json(doc, pages, extents, chapter_num)
    write_json(crops_path, crops)
    _summarize(chapter_num, crops, len(pages), check)

    if llm.preview:
        from remanga.extensions.llm_crop.preview import write_previews

        write_previews(cropper, project_name, chapter_num, crops, pages)
    if cropped_panels(project_name, chapter_num):
        console.print("[dim]This chapter was already cropped - run `crop --force` to cut the new crops.[/]")
    return ImportOutcome("imported", check=check)
