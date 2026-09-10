"""Pure geometry over one page's marks: the order a reader meets them.

No state, no I/O, no Flask - a list of mark dicts ({x, y, w, h, ...} in the
page image's pixels) in, the same dicts in reading order out. The Reorder
button (at every scope) and the auto-order switch both use this, so it lives
in exactly one place: a second copy of "which panel comes first" in the
browser, or in the cropper, is how two parts of remanga end up numbering the
same page differently.
"""

from __future__ import annotations

from functools import cmp_to_key
from typing import Any

Mark = dict[str, Any]

# How much two panels may overlap along an axis and still sit on opposite
# sides of a gutter. Real marks overlap a LOT: MAGI's boxes take in panel
# borders and bleed, and hand-drawn ones are drawn generously - neighbours on
# a real, narrated chapter overlapped by 20-70px, far past any fixed pixel
# allowance, which is exactly how a fixed 8px allowance found no gutters on
# those pages and fell through to a bad guess. So the allowance is relative:
# a quarter of the smaller of the two panels' extent on that axis, and never
# less than a few pixels.
GUTTER_TOLERANCE_PX = 8.0
OVERLAP_RATIO = 0.25

# Two panels no gutter separates are "in the same row" when their tops line up
# (within half of the shorter one's height) and they share at least half of
# its height. Overlap alone isn't enough: an inset slanting across the bottom
# edge of a big panel overlaps half of the inset, but its top is far below the
# big panel's, and a reader meets the big panel first.
SAME_ROW_RATIO = 0.5

# A panel counts as inside another when this much of its area is covered -
# an inset, which is read after the panel it sits in.
NESTED_RATIO = 0.9


def _split(marks: list[Mark], start: str, size: str) -> list[list[Mark]]:
    """Splits marks at every gutter that runs across all of them along one
    axis: a place where the next panel and the panel reaching furthest before
    it overlap by no more than the allowance above (a real gap qualifies
    trivially). Groups come back in ascending coordinate order; a single group
    means no gutter was found."""
    spans = sorted(((m[start], m[start] + m[size], m) for m in marks), key=lambda span: span[0])
    groups: list[list[Mark]] = []
    reach = float("-inf")
    reach_extent = 0.0
    for lo, hi, mark in spans:
        extent = hi - lo
        allowance = max(GUTTER_TOLERANCE_PX, OVERLAP_RATIO * min(extent, reach_extent))
        if not groups or reach - lo <= allowance:
            groups.append([])
        groups[-1].append(mark)
        if hi > reach:
            reach, reach_extent = hi, extent
    return groups


def _merge_gridded(columns: list[list[Mark]]) -> list[list[Mark]]:
    """Joins neighbouring columns back into one block when, together, they
    still have a horizontal gutter running across them - i.e. when they are
    really the columns of a grid, which is read row by row.

    Splitting at every vertical gutter at once would otherwise turn a tall
    panel beside a 2x2 grid into three columns, and the grid would be read
    down one column then down the next. Merging only ever joins neighbours in
    reading order, and the whole group can never merge back into one block:
    this is only reached when the whole group has no horizontal gutter."""
    blocks: list[list[Mark]] = [list(columns[0])]
    for column in columns[1:]:
        joined = blocks[-1] + column
        if len(_split(joined, "y", "h")) > 1:
            blocks[-1] = joined
        else:
            blocks.append(list(column))
    return blocks


def _nested(outer: Mark, inner: Mark) -> bool:
    iw = min(outer["x"] + outer["w"], inner["x"] + inner["w"]) - max(outer["x"], inner["x"])
    ih = min(outer["y"] + outer["h"], inner["y"] + inner["h"]) - max(outer["y"], inner["y"])
    if iw <= 0 or ih <= 0:
        return False
    inner_area = inner["w"] * inner["h"]
    return iw * ih >= NESTED_RATIO * inner_area and outer["w"] * outer["h"] > inner_area


def _fallback(marks: list[Mark], rtl: bool) -> list[Mark]:
    """Order for a group no gutter separates - panels that overlap, or sit
    inside one another. Decided pairwise, the way a reader decides: an inset
    comes after the panel it's in; two panels whose tops line up go in the
    reading direction; otherwise the higher one first.

    Never by raw top edge alone. Two panels in one row whose tops differ by a
    few pixels are still one row, and sorting by top put the left one first
    for no better reason than its top being 8px higher."""
    def compare(a: Mark, b: Mark) -> float:
        if _nested(a, b):
            return -1
        if _nested(b, a):
            return 1
        shorter = min(a["h"], b["h"])
        overlap = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
        if overlap >= SAME_ROW_RATIO * shorter and abs(a["y"] - b["y"]) <= SAME_ROW_RATIO * shorter:
            ax, bx = a["x"] + a["w"] / 2, b["x"] + b["w"] / 2
            return (bx - ax) if rtl else (ax - bx)
        return (a["y"] + a["h"] / 2) - (b["y"] + b["h"] / 2)

    return sorted(marks, key=cmp_to_key(lambda a, b: (compare(a, b) > 0) - (compare(a, b) < 0)))


def _xy_cut(marks: list[Mark], rtl: bool) -> list[Mark]:
    if len(marks) < 2:
        return list(marks)
    rows = _split(marks, "y", "h")
    if len(rows) > 1:
        return [m for row in rows for m in _xy_cut(row, rtl)]
    columns = _split(marks, "x", "w")
    if len(columns) > 1:
        if rtl:
            columns.reverse()
        blocks = _merge_gridded(columns)
        if len(blocks) == 1:  # can't happen (see _merge_gridded), but never recurse on the same group
            blocks = columns
        return [m for block in blocks for m in _xy_cut(block, rtl)]
    return _fallback(marks, rtl)


def reading_order(marks: list[Mark], direction: str = "right_to_left") -> list[Mark]:
    """The page's marks in the order a reader meets them.

    Recursive XY-cut, the way a reader actually splits a page: find a
    horizontal gutter running across every panel and read above it before
    below it; failing that, find a vertical gutter and read the side the
    reading direction starts on first (right for manga, left for webtoons,
    manhwa and Western comics); then do the same inside each part. A tall
    panel beside a stack is the tall panel then the stack, or the stack then
    the tall panel, depending only on which side it's on - and a grid beside
    a tall panel is read row by row, not column by column.

    Gutters are found with a relative overlap allowance (OVERLAP_RATIO), not
    a fixed number of pixels, because real marks overlap their neighbours by
    tens of pixels. A group with no gutter at all goes to _fallback.

    A genuinely irregular page - diagonal gutters, a panel breaking out across
    three others - has no single right answer, and this gives a sensible one
    rather than a guaranteed one. That is what turning auto-order off and
    dragging in the panel list is for."""
    return _xy_cut(list(marks), direction != "left_to_right")


def order_changed(before: list[Mark], after: list[Mark]) -> bool:
    return [id(m) for m in before] != [id(m) for m in after]
