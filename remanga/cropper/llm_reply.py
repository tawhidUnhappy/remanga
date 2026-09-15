"""Gemini's crops for a chapter: reading the reply pasted into llm_crops.json,
checking it against the chapter's real pages, turning it into crops.json, and
writing a fix request to paste back when it doesn't check out.

The reply's boxes are measured on the square grid images (llm_grid), so each
one is converted to the page's own 0-1000 box (PageExtent.to_page_box) before
it goes anywhere near crops.json. crops.json stays the one file the cropper,
the marker, `status` and `restart` read: an LLM crop is a panel entry with
`src: "llm"` and three extra keys that only the LLM crop path reads
(remanga.cropper.llm_boxes), with `box_1000` set to the rectangle around all
of them, so anything that only reads `box_1000` still sees the right crop.

Checks come in two strengths. An error means the reply can't be imported as
it stands - a page missing, a box that isn't a box - and produces a fix
request. A warning is something worth a look that may well be right (an
order that differs from the layout's XY-cut is often Gemini reading the
story), and never blocks the import."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.cropper.grid_bundles import ChapterPage, chapter_pages
from remanga.cropper.llm_grid import PageExtent, oriented_size, page_extent
from remanga.json_io import has_real_json_content, read_json_or, write_json
from remanga.paths import get_chapter_dir, get_llm_crop_dir, get_llm_crops_path, load_project_metadata

KINDS = ("panel", "group", "splash")
SKIP_REASONS = ("credits", "ad", "blank", "duplicate")
BOX_KEYS = ("frames", "text_outside", "art_outside")
CROP_KEYS = ("order", "kind", *BOX_KEYS)
LLM_SRC = "llm"
FIX_REQUEST_NAME = "fix_request.md"

# How many problems are printed before "... and N more" - the fix request
# always carries every one of them.
_PRINT_LIMIT = 12


@dataclass
class ReplyCheck:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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


def _same_chapter(a: Any, b: Any) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def _box_problem(box: Any) -> str | None:
    if (not isinstance(box, list) or len(box) != 4
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box)):
        return "is not a list of four numbers"
    if any(v < 0 or v > 1000 for v in box):
        return "has a value outside 0-1000"
    ymin, xmin, ymax, xmax = box
    if ymin >= ymax:
        return f"has ymin {ymin}, which is not below its ymax {ymax}"
    if xmin >= xmax:
        return f"has xmin {xmin}, which is not left of its xmax {xmax}"
    return None


def _bbox(boxes: list[list[float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _overlap(a: list[float], b: list[float]) -> float:
    return _area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def _check_page(entry: dict[str, Any], extent: PageExtent, check: ReplyCheck) -> bool:
    """Adds one page's errors; True when the page is sound enough to also
    look at its layout."""
    stem = entry["page"]
    story, crops = entry.get("story"), entry.get("crops")
    if not isinstance(story, bool):
        check.errors.append(f'{stem}: "story" must be true or false')
        return False
    if not isinstance(crops, list):
        check.errors.append(f'{stem}: "crops" must be a list')
        return False
    if not story:
        if entry.get("skip") not in SKIP_REASONS:
            check.errors.append(f"{stem}: a page that is not part of the story needs a skip of "
                                f"{', '.join(SKIP_REASONS)} (got {entry.get('skip')!r})")
        if crops:
            check.errors.append(f"{stem}: a skipped page must have no crops")
        return False
    if not crops:
        check.errors.append(f"{stem}: a story page needs at least one crop")
        return False

    before = len(check.errors)
    orders = [crop.get("order") if isinstance(crop, dict) else None for crop in crops]
    if orders != list(range(1, len(crops) + 1)):
        check.errors.append(f"{stem}: crop order numbers are {orders}, not 1 to {len(crops)}")
    for position, crop in enumerate(crops, start=1):
        if not isinstance(crop, dict):
            check.errors.append(f"{stem}: crop {position} is not an object")
            continue
        label = f"{stem} crop {crop.get('order', position)}"
        kind, frames = crop.get("kind"), crop.get("frames")
        if kind not in KINDS:
            check.errors.append(f"{label}: kind must be panel, group or splash, not {kind!r}")
        if not isinstance(frames, list) or not frames:
            check.errors.append(f"{label}: has no frames")
            continue
        if kind == "group" and len(frames) < 2:
            check.errors.append(f"{label}: a group needs two or more frames, it has {len(frames)}")
        if kind in ("panel", "splash") and len(frames) != 1:
            check.errors.append(f"{label}: a {kind} has exactly one frame, it has {len(frames)}")
        for key in BOX_KEYS:
            boxes = crop.get(key, [])
            if not isinstance(boxes, list):
                check.errors.append(f"{label}: {key} must be a list of boxes")
                continue
            for n, box in enumerate(boxes):
                problem = _box_problem(box)
                if problem:
                    check.errors.append(f"{label}: {key}[{n}] {problem}")
                elif box[0] >= extent.ymax or box[1] >= extent.xmax:
                    check.errors.append(f"{label}: {key}[{n}] {box} lies in the black padding, outside the "
                                        f"page (the page area is {extent.box})")
        unknown = sorted(set(crop) - set(CROP_KEYS))
        if unknown:
            check.warnings.append(f"{label}: ignored unknown key(s) {', '.join(unknown)}")
    return len(check.errors) == before


def _layout_warnings(stem: str, crops: list[dict[str, Any]], direction: str) -> list[str]:
    """Things about a sound page worth a look. Measured on the square, where
    a unit is the same size across and down, so shapes compare directly."""
    from remanga.webui.mark_ops import reading_order

    warnings = []
    frames = [(crop["order"], box) for crop in crops for box in crop["frames"]]
    for i, (order_a, a) in enumerate(frames):
        for order_b, b in frames[i + 1:]:
            union = _area(a) + _area(b) - _overlap(a, b)
            if order_a != order_b and union and _overlap(a, b) / union >= 0.6:
                warnings.append(f"{stem}: crops {order_a} and {order_b} have nearly the same frame")

    for crop in crops:
        if crop["kind"] != "group":
            continue
        rect = _bbox(crop["frames"])
        swallowed = [other["order"] for other in crops if other is not crop
                     and any(_overlap(rect, f) > 0.5 * _area(f) for f in other["frames"])]
        if swallowed:
            warnings.append(f"{stem}: group {crop['order']}'s rectangle takes in most of crop(s) "
                            f"{', '.join(map(str, swallowed))}, which will be painted out of it")
        height, width = rect[2] - rect[0], rect[3] - rect[1]
        if width and height > 2 * width:
            warnings.append(f"{stem}: group {crop['order']} is {height / width:.1f}x taller than it is wide")

    values = [v for crop in crops for key in BOX_KEYS for box in crop.get(key, []) for v in box if v not in (0, 1000)]
    if len(values) >= 8 and sum(v % 50 == 0 for v in values) >= 0.7 * len(values):
        warnings.append(f"{stem}: most coordinates sit exactly on grid lines - rounded rather than measured?")

    rects = [_bbox([b for key in BOX_KEYS for b in crop.get(key, [])]) for crop in crops]
    marks = [{"id": str(crop["order"]), "x": r[1], "y": r[0], "w": r[3] - r[1], "h": r[2] - r[0]}
             for crop, r in zip(crops, rects, strict=True)]
    layout = [mark["id"] for mark in reading_order(marks, direction)]
    if len(marks) > 1 and layout != [mark["id"] for mark in marks]:
        warnings.append(f"{stem}: the order differs from the layout's reading order ({', '.join(layout)}) - "
                        f"right when the story decides it, but worth a look")
    return warnings


def check_reply(doc: Any, pages: list[ChapterPage], extents: dict[str, PageExtent],
                chapter_num: str, direction: str) -> ReplyCheck:
    check = ReplyCheck()
    if not isinstance(doc, dict) or not isinstance(doc.get("pages"), list):
        check.errors.append('the reply is not a JSON object with a "pages" list')
        return check
    if "chapter" in doc and not _same_chapter(doc["chapter"], chapter_num):
        check.warnings.append(
            f"the reply says chapter {doc['chapter']!r}, but it was pasted into chapter {chapter_num}"
        )
    check.warnings.extend(f"Gemini reported: {problem}" for problem in doc.get("problems") or [])

    known = {page.stem for page in pages}
    seen: list[str] = []
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
        if _check_page(entry, extents[stem], check) and entry["story"]:
            check.warnings.extend(_layout_warnings(stem, entry["crops"], direction))

    missing = [page.stem for page in pages if page.stem not in seen]
    if missing:
        check.errors.append(f"page(s) missing from pages: {', '.join(missing)}")
    elif seen != [page.stem for page in pages]:
        check.warnings.append("pages are not in page order - they are put back in order on import")
    return check


def to_crops_json(doc: dict[str, Any], pages: list[ChapterPage], extents: dict[str, PageExtent],
                  chapter_num: str) -> dict[str, Any]:
    """A checked reply as crops.json, every box converted to its page."""
    from remanga.webui.marker_state import DECIDED_KEY, FORMAT_KEY, MARKS_FORMAT

    entries = {entry["page"]: entry for entry in doc["pages"]}
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
            rect = _bbox([box for key in BOX_KEYS for box in boxes[key]])
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


def import_llm_crops(cropper: CropperConfig, project_name: str, chapter_num: str, *,
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
        check = check_reply(doc, pages, extents, chapter_num, direction)
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

    story = [page for page in crops["pages"] if page["is_story_page"]]
    panels = [panel for page in story for panel in page["panels"]]
    skipped: dict[str, int] = {}
    for page in crops["pages"]:
        if not page["is_story_page"]:
            skipped[page["skip_reason"]] = skipped.get(page["skip_reason"], 0) + 1
    console.print(
        f"[bold green]✓ Chapter {chapter_num}: crops.json written from Gemini's reply[/] "
        f"[dim]({len(pages)} pages · {len(panels)} crops, "
        f"{sum(panel['kind'] == 'group' for panel in panels)} of them groups"
        + (f" · skipped {', '.join(f'{n} {reason}' for reason, n in skipped.items())}" if skipped else "")
        + ")[/]"
    )
    if check.warnings:
        console.print(f"[yellow]{len(check.warnings)} thing(s) worth a look:[/]")
        _print_lines(check.warnings, "yellow")

    if cropper.llm_crop.preview:
        from remanga.cropper.llm_preview import write_previews

        write_previews(cropper, project_name, chapter_num, crops, pages)
    if cropped_panels(project_name, chapter_num):
        console.print("[dim]This chapter was already cropped - run `crop --force` to cut the new crops.[/]")
    return ImportOutcome("imported", check=check)
