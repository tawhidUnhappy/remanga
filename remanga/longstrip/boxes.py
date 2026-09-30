"""MAGI's panels on a long-strip page, made to fit how webtoons are drawn.

MAGI was trained on printed manga, where the words are inside the panel
borders. A webtoon floats them in the white between panels instead, often
with no border around the art at all, and a gradient fading one scene into
the next looks like a panel to it. Measured on a real chapter's pages: a
bubble over its panel left outside the box (so its words never reached the
PDF), and a black-to-white fade boxed as a panel of its own.

So on a long-strip page, after MAGI:
- a box over nothing but blank rows (flat colour across the width - which is
  what a fade is, row by row) is dropped;
- rows of art that no box covers - a floating bubble, a sound effect, the
  top of a bubble that overlaps its panel's border - are added to the box
  nearest them, above or below - or, when there is a whole panel's worth of
  it, become a box of their own;
- a page MAGI found nothing on gets one box per block of art, so it never
  comes back empty while it has art on it."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from remanga.longstrip.gaps import BLANK_ROW_STD, SMALL_BLOCK_SHARE, glued_blocks, row_spread

Box = list[float]  # [x1, y1, x2, y2] in page pixels

# A box is kept when at least this share of its rows has art in it.
MIN_ART_ROWS = 0.05
# Uncovered art shorter than this is JPEG noise at a box's edge, not art.
MIN_RUN_PX = 4


def _columns(gray: np.ndarray, y0: int, y1: int) -> tuple[int, int]:
    """The left and right edge of the art in rows [y0, y1)."""
    busy = np.flatnonzero(gray[y0:y1].astype(np.float32).std(axis=0) > BLANK_ROW_STD)
    return (int(busy[0]), int(busy[-1]) + 1) if busy.size else (0, gray.shape[1])


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def fit_boxes(page: Path, boxes: list[Box], texts: list[Box] = ()) -> list[Box]:
    """`boxes` (MAGI's, for this page) fitted to the page's art - see the
    module doc - and then to `texts`, MAGI's text boxes (keep_texts_whole).
    Order is kept."""
    with Image.open(page) as img:
        gray = np.asarray(img.convert("L"))
    height, width = gray.shape
    spread = row_spread(gray)
    art = spread > BLANK_ROW_STD

    kept = [list(map(float, b)) for b in boxes
            if art[max(0, int(b[1])):max(int(b[1]) + 1, int(b[3]))].mean() >= MIN_ART_ROWS]
    if not kept:
        return [[float(x0), float(y0), float(x1), float(y1)]
                for y0, y1 in glued_blocks(spread, width)
                for x0, x1 in [_columns(gray, y0, y1)]]

    covered = np.zeros(height, dtype=bool)
    for b in kept:
        covered[max(0, int(b[1])):int(np.ceil(b[3]))] = True
    for y0, y1 in _runs(art & ~covered):
        x0, x1 = _columns(gray, y0, y1)
        if y1 - y0 >= width * SMALL_BLOCK_SHARE:
            # A whole panel MAGI missed, not a bubble: a box of its own, in
            # its place top to bottom.
            at = next((i for i, b in enumerate(kept) if b[1] > y0), len(kept))
            kept.insert(at, [float(x0), float(y0), float(x1), float(y1)])
            continue
        nearest = min(kept, key=lambda b: max(b[1] - y1, y0 - b[3], 0))
        nearest[0], nearest[1] = min(nearest[0], x0), min(nearest[1], y0)
        nearest[2], nearest[3] = max(nearest[2], x1), max(nearest[3], y1)
    return keep_texts_whole(kept, texts)


def keep_texts_whole(boxes: list[Box], texts: list[Box]) -> list[Box]:
    """Every text box inside one panel, whole. A webtoon bubble often sits
    across the line between two panels, and MAGI's panel edge goes straight
    through it - measured: "...Lord Rae, will now enter" came out as the
    bottom half of one panel and the top half of the next, so neither panel
    had words that read. The bubble goes to the panel already holding most of
    its rows, which grows to take all of it; a panel it also cut into gives
    those rows up, unless that would cost it half its height (then the bubble
    really is inside it, beside the art, and it stays)."""
    for t in texts:
        if not boxes:
            break
        owner = max(boxes, key=lambda b: (_overlap(b[1], b[3], t[1], t[3]), -abs(b[1] - t[1])))
        if _overlap(owner[1], owner[3], t[1], t[3]) == 0:
            owner = min(boxes, key=lambda b: max(b[1] - t[3], t[1] - b[3], 0))
        owner[0], owner[1] = min(owner[0], t[0]), min(owner[1], t[1])
        owner[2], owner[3] = max(owner[2], t[2]), max(owner[3], t[3])
        for other in boxes:
            if other is owner or not _overlap(other[0], other[2], t[0], t[2]) \
                    or not _overlap(other[1], other[3], t[1], t[3]):
                continue
            height = other[3] - other[1]
            if other[1] > owner[1] and other[3] - t[3] >= height / 2:
                other[1] = t[3]
            elif other[1] < owner[1] and t[1] - other[1] >= height / 2:
                other[3] = t[1]
    return boxes


def _runs(rows: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) of each run of True at least MIN_RUN_PX long."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], rows.astype(np.int8), [0]))))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2], strict=True) if b - a >= MIN_RUN_PX]
