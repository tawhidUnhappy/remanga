"""Checking Gemini's crops for a chapter against the chapter's real pages.

Checks come in two strengths. An error means the reply can't be imported as
it stands - a page missing, a box that isn't a box - and produces a fix
request (reply_import). A warning is something worth a look that may well be
right (an order that differs from the layout's XY-cut is often Gemini reading
the story), and never blocks the import.

Boxes are checked as Gemini wrote them: on the square grid image, where a
unit is the same size across and down, so shapes compare directly. A reply
can instead declare `"units": "page"` - boxes normalised to the page itself,
crops.json's own `box_1000` - for a model that measures on the plain pages
(or from MAGI's boxes) and never saw a grid; shapes are then scaled back to
the page's real proportions before they're compared."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from remanga.extensions.llm_crop.bundles import ChapterPage
from remanga.extensions.llm_crop.grid import PageExtent

KINDS = ("panel", "group", "splash")
SKIP_REASONS = ("credits", "ad", "blank", "duplicate")
BOX_KEYS = ("frames", "text_outside", "art_outside")
CROP_KEYS = ("order", "kind", *BOX_KEYS)
GRID_UNITS, PAGE_UNITS = "grid", "page"
UNITS = (GRID_UNITS, PAGE_UNITS)
# A page measured in its own units: the whole 0-1000 range, and converting a
# box to crops.json's box_1000 changes nothing.
WHOLE_PAGE = PageExtent(1000.0, 1000.0)


@dataclass
class ReplyCheck:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def box_bounds(boxes: list[list[float]]) -> list[float]:
    """The rectangle around `[ymin, xmin, ymax, xmax]` boxes."""
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def reply_units(doc: Any) -> str:
    """The units the reply's boxes are measured in - `grid` unless it says."""
    return doc.get("units", GRID_UNITS) if isinstance(doc, dict) else GRID_UNITS


def box_extents(doc: Any, extents: dict[str, PageExtent]) -> dict[str, PageExtent]:
    """Each page's extent in the reply's own units: its area on the square
    for a grid reply, the whole 0-1000 range for a page-units one."""
    if reply_units(doc) == PAGE_UNITS:
        return dict.fromkeys(extents, WHOLE_PAGE)
    return extents


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


def _area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _overlap(a: list[float], b: list[float]) -> float:
    return _area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def _check_crop(label: str, crop: dict[str, Any], extent: PageExtent, check: ReplyCheck) -> None:
    kind, frames = crop.get("kind"), crop.get("frames")
    if kind not in KINDS:
        check.errors.append(f"{label}: kind must be panel, group or splash, not {kind!r}")
    if not isinstance(frames, list) or not frames:
        check.errors.append(f"{label}: has no frames")
        return
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
        _check_crop(f"{stem} crop {crop.get('order', position)}", crop, extent, check)
    return len(check.errors) == before


def _layout_warnings(stem: str, crops: list[dict[str, Any]], direction: str,
                     y_per_x: float = 1.0, measured_on_grid: bool = True) -> list[str]:
    """Things about a sound page worth a look. `y_per_x` turns a box's height
    into the same scale as its width - 1 on the square grid, the page's own
    height-to-width ratio for a page-units reply."""
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
        rect = box_bounds(crop["frames"])
        swallowed = [other["order"] for other in crops if other is not crop
                     and any(_overlap(rect, f) > 0.5 * _area(f) for f in other["frames"])]
        if swallowed:
            warnings.append(f"{stem}: group {crop['order']}'s rectangle takes in most of crop(s) "
                            f"{', '.join(map(str, swallowed))}, which will be painted out of it")
        height, width = (rect[2] - rect[0]) * y_per_x, rect[3] - rect[1]
        if width and height > 2 * width:
            warnings.append(f"{stem}: group {crop['order']} is {height / width:.1f}x taller than it is wide")

    values = [v for crop in crops for key in BOX_KEYS for box in crop.get(key, []) for v in box if v not in (0, 1000)]
    if measured_on_grid and len(values) >= 8 and sum(v % 50 == 0 for v in values) >= 0.7 * len(values):
        warnings.append(f"{stem}: most coordinates sit exactly on grid lines - rounded rather than measured?")

    rects = [box_bounds([b for key in BOX_KEYS for b in crop.get(key, [])]) for crop in crops]
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
    units = reply_units(doc)
    if units not in UNITS:
        check.errors.append(f'"units" must be "grid" (boxes measured on the grid squares) or "page" '
                            f'(boxes normalised to the page itself), not {units!r}')
        return check
    measured = box_extents(doc, extents)

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
        if _check_page(entry, measured[stem], check) and entry["story"]:
            real = extents[stem]
            y_per_x = real.ymax / real.xmax if units == PAGE_UNITS else 1.0
            check.warnings.extend(_layout_warnings(stem, entry["crops"], direction, y_per_x,
                                                   measured_on_grid=units == GRID_UNITS))

    missing = [page.stem for page in pages if page.stem not in seen]
    if missing:
        check.errors.append(f"page(s) missing from pages: {', '.join(missing)}")
    elif seen != [page.stem for page in pages]:
        check.warnings.append("pages are not in page order - they are put back in order on import")
    return check
