"""Tall pictures split where they are calm - the way the user splits a long
continuous image into pieces that can each be narrated.

Measured on their own marks: where they split one continuous picture, the
row was quieter than 92-99% of the rows within 400 of it. So a picture taller
than TALL x its width is cut at its calmest stretch in the middle part, and
only when that stretch really is calm (energy under CALM_SHARE of the
picture's own median). Never forced: a picture with no calm stretch stays
whole - better one tall panel than a cut through a face (the old splitter
cut at a fixed point whatever was there, and that was the complaint)."""

from __future__ import annotations

import numpy as np

TALL = 1.8              # height / width above which a picture is split
MIDDLE = (0.25, 0.75)   # where in the picture a cut may go
CALM_SHARE = 0.25
MIN_PIECE = 0.6         # height / width a piece must keep


def split_tall(top: int, bottom: int, energy: np.ndarray, width: int) -> list[tuple[int, int]]:
    height = bottom - top
    if height <= TALL * width:
        return [(top, bottom)]
    lo = top + max(int(MIDDLE[0] * height), int(MIN_PIECE * width))
    hi = top + min(int(MIDDLE[1] * height), height - int(MIN_PIECE * width))
    if hi <= lo:
        return [(top, bottom)]
    window = energy[lo:hi]
    y = lo + int(np.argmin(window))
    if energy[y] > CALM_SHARE * float(np.median(energy[top:bottom])):
        return [(top, bottom)]
    return split_tall(top, y, energy, width) + split_tall(y, bottom, energy, width)
