"""Pure geometry over one page's marks: reading order, and deciding which
marks are MAGI's own.

No state, no I/O, no Flask - a list of mark dicts ({x, y, w, h, src, ...} in
the page image's pixels) in, a list out. Both operations are used at every
scope the marker offers (a page, a chapter, a range, the whole session) and by
the auto-order switch, so they live in exactly one place: a second copy of
"which panel comes first" in the browser, or in the cropper, is how two parts
of remanga end up numbering the same page differently.
"""

from __future__ import annotations

from typing import Any

Mark = dict[str, Any]

# How closely a mark must overlap one of MAGI's boxes to count as that box.
# Not 1.0: a mark read back from crops.json has been through box_1000, whose
# integer rounding moves each edge by up to about a pixel - measured, a
# 100x100 panel survives the round trip at IoU ~0.95 and a typical 300x300 one
# at ~0.98. 0.9 sits above that noise and below any adjustment a person makes
# on purpose, which is the only distinction relabelling exists to draw.
AI_MATCH_IOU = 0.9


# How far a mark may overhang a gutter and still count as not crossing it.
# Hand-drawn marks and MAGI's boxes both routinely bleed a few pixels past a
# panel border; without slack, a 3px overhang hides the gutter and the page
# stops splitting where a reader's eye obviously does. Capped at a tenth of
# the mark so a small panel isn't shrunk to nothing.
GUTTER_TOLERANCE_PX = 8.0


def _split(marks: list[Mark], start: str, size: str) -> list[list[Mark]]:
    """Splits marks wherever a gutter runs clean across all of them along one
    axis - a coordinate no mark covers, allowing GUTTER_TOLERANCE_PX of
    overhang. Groups come back in ascending coordinate order; a single group
    means there is no such gutter."""
    spans = []
    for mark in marks:
        lo, hi = mark[start], mark[start] + mark[size]
        slack = min(GUTTER_TOLERANCE_PX, (hi - lo) * 0.1)
        spans.append((lo + slack, hi - slack, mark))
    spans.sort(key=lambda span: span[0])
    groups: list[list[Mark]] = []
    reach = float("-inf")
    for lo, hi, mark in spans:
        if not groups or lo >= reach:
            groups.append([])
        groups[-1].append(mark)
        reach = max(reach, hi)
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
    # No gutter runs clean across this group either way: panels overlap or
    # sit inside one another. Top first, then the reading direction, is the
    # least surprising guess.
    return sorted(marks, key=lambda m: (m["y"], -m["x"] if rtl else m["x"]))


def reading_order(marks: list[Mark], direction: str = "right_to_left") -> list[Mark]:
    """The page's marks in the order a reader meets them.

    Recursive XY-cut, the way a reader actually splits a page: find a
    horizontal gutter that runs clean across every panel and read above it
    before below it; failing that, find a vertical gutter and read the side
    the reading direction starts on first (right for manga, left for
    webtoons, manhwa and Western comics); then do the same inside each part.
    So a tall panel beside a stack is the tall panel then the stack, or the
    stack then the tall panel, depending only on which side it's on - and a
    grid beside a tall panel is read row by row, not column by column.

    An earlier version grouped rows by whether a panel's centre fell inside
    the row found so far, which depended on the order panels arrived in: a
    tall right-hand panel beside two stacked left ones came out as the top
    left, then the tall one, then the bottom left.

    A genuinely irregular page - diagonal gutters, a panel breaking out across
    three others - has no single right answer, and this gives a sensible one
    rather than a guaranteed one. That is what the drag handle in the panel
    list is for."""
    return _xy_cut(list(marks), direction != "left_to_right")


def order_changed(before: list[Mark], after: list[Mark]) -> bool:
    return [id(m) for m in before] != [id(m) for m in after]


def iou(mark: Mark, box: list[float]) -> float:
    """Intersection over union of a mark ({x,y,w,h}) and a MAGI box
    ([x1, y1, x2, y2]), both in the page's pixels."""
    ax1, ay1, ax2, ay2 = mark["x"], mark["y"], mark["x"] + mark["w"], mark["y"] + mark["h"]
    bx1, by1, bx2, by2 = box
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def relabel(marks: list[Mark], ai_boxes: list[list[float]], threshold: float = AI_MATCH_IOU) -> int:
    """Sets each mark's `src` by comparing it with what MAGI produced for the
    page: "ai" if it is still essentially one of MAGI's boxes, "manual"
    otherwise. Returns how many marks changed label. Mutates in place.

    Matching is one-to-one and best-first: every (mark, box) pair above the
    threshold is ranked by overlap and taken in that order, each box used
    once. Without that, two near-duplicate marks sitting on one detected
    panel would both be called MAGI's, when at most one of them can be."""
    pairs = sorted(
        ((iou(mark, box), mi, bi)
         for mi, mark in enumerate(marks)
         for bi, box in enumerate(ai_boxes)),
        reverse=True,
    )
    matched_marks: set[int] = set()
    used_boxes: set[int] = set()
    for score, mi, bi in pairs:
        if score < threshold:
            break
        if mi in matched_marks or bi in used_boxes:
            continue
        matched_marks.add(mi)
        used_boxes.add(bi)

    changed = 0
    for mi, mark in enumerate(marks):
        label = "ai" if mi in matched_marks else "manual"
        if mark.get("src") != label:
            mark["src"] = label
            changed += 1
    return changed
