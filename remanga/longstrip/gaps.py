"""Where a long strip can be cut: the blank bands between its panels.

A webtoon chapter arrives as a handful of very tall images (720x9000 is
typical) sliced wherever the uploader's tool felt like it - straight through a
panel as often as not. The only cuts that never split a panel are the ones the
artist left: rows of flat colour (white, black, any tint) running the full
width. This finds them and packs the art between them into pages about the
shape of a manga page, which is what the Panel Marker and MAGI were built
for.

Pure arrays in, row numbers out - nothing here opens a file."""

from __future__ import annotations

from itertools import pairwise

import numpy as np

# A row is blank when its grey levels barely vary across the width. JPEG noise
# on a white gutter measures 0.5-2; the faintest art (a pale sky gradient with a
# line through it) is well over 6.
BLANK_ROW_STD = 4.0
# A band has to be this tall (as a share of the width, never under 6px) to be a
# gutter: a single flat row inside a panel - a horizon, a ruled line - is not.
MIN_GAP_SHARE = 0.015
MIN_GAP_PX = 6
# A block of art shorter than this (as a share of the width) is a speech bubble,
# a sound effect or the tail of one floating in the gutter - it belongs with the
# panel across the narrower gap, never on a page by itself.
SMALL_BLOCK_SHARE = 0.45
# Pages are packed up to about a manga page's shape (height / width).
TARGET_ASPECT = 1.45
# Art that runs this far (height / width) without a single gutter is cut
# anyway, at the quietest row near the limit - a page 10x taller than it is
# wide can't be marked or shown.
MAX_ASPECT = 4.0


def row_spread(gray: np.ndarray) -> np.ndarray:
    """Each row's standard deviation of grey level - the per-row fact every
    other function here works from. `gray` is (height, width), any number
    type."""
    return gray.astype(np.float32).std(axis=1)


def find_gaps(spread: np.ndarray, width: int) -> list[tuple[int, int]]:
    """The blank bands, as [start, end) row ranges, including any at the very
    top or bottom."""
    min_gap = max(MIN_GAP_PX, round(width * MIN_GAP_SHARE))
    blank = spread <= BLANK_ROW_STD
    gaps: list[tuple[int, int]] = []
    start = None
    for y, is_blank in enumerate(blank):
        if is_blank and start is None:
            start = y
        elif not is_blank and start is not None:
            if y - start >= min_gap:
                gaps.append((start, y))
            start = None
    if start is not None and len(blank) - start >= min_gap:
        gaps.append((start, len(blank)))
    return gaps


def content_blocks(spread: np.ndarray, width: int) -> list[tuple[int, int]]:
    """The art between the gaps, as [start, end) row ranges."""
    blocks: list[tuple[int, int]] = []
    y = 0
    for g0, g1 in find_gaps(spread, width):
        if g0 > y:
            blocks.append((y, g0))
        y = g1
    if y < len(spread):
        blocks.append((y, len(spread)))
    return blocks


def glued_blocks(spread: np.ndarray, width: int) -> list[tuple[int, int]]:
    """content_blocks with every small one joined to the neighbour across its
    narrower gap. A block joined this way can still be large - a run of
    bubbles becomes one conversation with the panel it floats nearest."""
    blocks = content_blocks(spread, width)
    if len(blocks) < 2:
        return blocks
    small = [b1 - b0 < width * SMALL_BLOCK_SHARE for b0, b1 in blocks]
    gap = [nxt[0] - prev[1] for prev, nxt in pairwise(blocks)]  # gap[i] is below block i
    glue = [False] * len(gap)
    for i, is_small in enumerate(small):
        if not is_small:
            continue
        above = gap[i - 1] if i > 0 else None
        below = gap[i] if i < len(gap) else None
        if below is not None and (above is None or below < above):
            glue[i] = True
        elif above is not None:
            glue[i - 1] = True
    units = [list(blocks[0])]
    for block, glued in zip(blocks[1:], glue, strict=True):
        if glued:
            units[-1][1] = block[1]
        else:
            units.append(list(block))
    return [(u0, u1) for u0, u1 in units]


def _split_tall(block: tuple[int, int], spread: np.ndarray, width: int) -> list[tuple[int, int]]:
    """A block past MAX_ASPECT, cut at the quietest row in the last quarter
    before each limit - the least art lost to a cut that has to happen."""
    limit = round(width * MAX_ASPECT)
    top, bottom = block
    pieces = []
    while bottom - top > limit:
        window = spread[top + limit * 3 // 4: top + limit]
        cut = top + limit * 3 // 4 + int(np.argmin(window))
        pieces.append((top, cut))
        top = cut
    pieces.append((top, bottom))
    return pieces


def plan_pages(spread: np.ndarray, width: int) -> list[tuple[int, int]]:
    """The strip as pages: [start, end) row ranges that tile it top to bottom
    with no row lost, each cut in the middle of a gutter. Blocks are packed in
    order until the next one would take the page past TARGET_ASPECT; a block
    taller than that on its own is a page on its own. Small blocks are glued
    to their panel first (glued_blocks), so a bubble never makes a page alone. Blank rows at the very
    top and bottom stay with the first and last page."""
    height = len(spread)
    blocks = [piece for block in glued_blocks(spread, width) for piece in _split_tall(block, spread, width)]
    if not blocks:
        return [(0, height)] if height else []
    target = width * TARGET_ASPECT
    groups: list[list[tuple[int, int]]] = [[blocks[0]]]
    for block in blocks[1:]:
        if block[1] - groups[-1][0][0] > target:
            groups.append([block])
        else:
            groups[-1].append(block)
    # Each cut lands halfway across the gutter between two groups, so both
    # pages keep a margin of their own.
    cuts = [0] + [(prev[-1][1] + nxt[0][0]) // 2 for prev, nxt in pairwise(groups)] + [height]
    return list(pairwise(cuts))
