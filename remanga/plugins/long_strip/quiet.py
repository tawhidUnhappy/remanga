"""Tall pictures split where they are calm - the way the user splits a long
continuous image into pieces that can each be narrated.

Measured on their own marks: where they split one continuous picture, the
row was quieter than 92-99% of the rows within 400 of it. So a picture taller
than TALL x its width is cut at its calmest stretch in the middle part, and
only when that stretch really is calm (energy under CALM_SHARE of the
picture's own median). Never forced: a picture with no calm stretch stays
whole - better one tall panel than a cut through a face (the old splitter
cut at a fixed point whatever was there, and that was the complaint).

A strong border (borders.py) in that middle part is taken before any calm
stretch: two pictures meeting with no gutter is the best place to split.
Borders only ever split a picture that is too tall - see detect.py."""

from __future__ import annotations

import numpy as np

TALL = 1.8              # height / width above which a picture is split
MIDDLE = (0.25, 0.75)   # where in the picture a cut may go
CALM_SHARE = 0.12       # 0.25 until 2026-10-27: cut tall pictures through figures (detect.py)
MIN_PIECE = 0.6         # height / width a piece must keep


def split_tall(top: int, bottom: int, energy: np.ndarray, width: int,
               borders: list[tuple[int, float]] = ()) -> list[tuple[int, int]]:
    """[top, bottom) as pieces no taller than TALL x width where it can be;
    `borders` are (row, score) of strong borders, preferred over calm."""
    height = bottom - top
    if height <= TALL * width:
        return [(top, bottom)]
    lo = top + max(int(MIDDLE[0] * height), int(MIN_PIECE * width))
    hi = top + min(int(MIDDLE[1] * height), height - int(MIN_PIECE * width))
    if hi <= lo:
        return [(top, bottom)]
    inside = [(score, y) for y, score in borders if lo <= y < hi]
    if inside:
        y = max(inside)[1]
    else:
        y = lo + int(np.argmin(energy[lo:hi]))
        if energy[y] > CALM_SHARE * float(np.median(energy[top:bottom])):
            return [(top, bottom)]
    return split_tall(top, y, energy, width, borders) + split_tall(y, bottom, energy, width, borders)
