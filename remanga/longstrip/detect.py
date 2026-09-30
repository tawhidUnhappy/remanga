"""A long strip's panels, proposed: the art between verified gutters
(gutters.py), with a few repairs, as [top, bottom) rows of one run.

- A block of art shorter than SMALL_SHARE x the width - a bubble or a sound
  effect floating between two gutters - is joined to the neighbour across the
  narrower gutter instead of becoming a panel of its own.
- A block with no busy row at all (a plain fade, blank paper) is no panel.
- A panel taller than MAX_RATIO x the width is cut into ~TARGET_HEIGHT pieces
  at the quietest band of rows near each even point (mangaEasy's auto-split,
  kept as it was); a cut that found no quiet band went through art and is
  reported as forced, so the Strip Marker can show it for checking."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
from PIL import Image

from remanga.longstrip.gutters import Gutter, verified_gutters

Range = tuple[int, int]

SMALL_SHARE = 0.45
FEATURELESS_STD = 4.0
PADDING = 2
# mangaEasy webtoon.py's auto-split defaults.
MAX_RATIO = 2.2
TARGET_HEIGHT = 1300
MIN_SEGMENT = 520
CUT_WINDOW = 380
ENERGY_THRESHOLD = 22.0


@dataclass
class Detection:
    panels: list[Range] = field(default_factory=list)
    gutters: list[Gutter] = field(default_factory=list)
    forced: list[int] = field(default_factory=list)   # auto-split rows that cut through art


def _blocks(height: int, gutters: list[Gutter]) -> list[Range]:
    """The art between the gutters, padded a little into each."""
    edges = [0] + [y for g in gutters for y in (g.top, g.bottom)] + [height]
    blocks = []
    for top, bottom in zip(edges[::2], edges[1::2], strict=True):
        top, bottom = max(0, top - PADDING), min(height, bottom + PADDING)
        if bottom > top:
            blocks.append((top, bottom))
    return blocks


def _glue_small(blocks: list[Range], width: int) -> list[Range]:
    """Small blocks joined to the neighbour across the narrower gap."""
    if len(blocks) < 2:
        return blocks
    small = [b - t < width * SMALL_SHARE for t, b in blocks]
    gaps = [nxt[0] - prev[1] for prev, nxt in pairwise(blocks)]   # gaps[i] is below block i
    join = [False] * len(gaps)
    for i, is_small in enumerate(small):
        if not is_small:
            continue
        above = gaps[i - 1] if i > 0 else None
        below = gaps[i] if i < len(gaps) else None
        if below is not None and (above is None or below < above):
            join[i] = True
        elif above is not None:
            join[i - 1] = True
    out = [list(blocks[0])]
    for block, joined in zip(blocks[1:], join, strict=True):
        if joined:
            out[-1][1] = block[1]
        else:
            out.append(list(block))
    return [(t, b) for t, b in out]


def row_std(gray: np.ndarray) -> np.ndarray:
    """Per-row busyness: the grey level's spread across the width (every third
    column, as mangaEasy measures it)."""
    return gray.astype(np.float32)[:, ::3].std(axis=1)


def band_energy(raw_std: np.ndarray, half_band: int = 24) -> np.ndarray:
    """Rolling max of row energy over +/-half_band rows: a cut is only safe in
    a band of quiet rows as wide as a real gutter (one quiet row is often the
    inside of a big bubble)."""
    if raw_std.size == 0:
        return raw_std
    padded = np.pad(raw_std, half_band, mode="edge")
    return np.lib.stride_tricks.sliding_window_view(padded, 2 * half_band + 1).max(axis=1)


def auto_split(ranges: list[Range], energy: np.ndarray, width: int) -> tuple[list[Range], list[int]]:
    out: list[Range] = []
    forced: list[int] = []
    for top, bottom in ranges:
        height = bottom - top
        if height <= MAX_RATIO * width:
            out.append((top, bottom))
            continue
        pieces = max(2, round(height / TARGET_HEIGHT))
        cuts: list[int] = []
        prev = top
        for k in range(1, pieces):
            target = top + height * k // pieces
            lo, hi = max(prev + MIN_SEGMENT, target - CUT_WINDOW), min(bottom - MIN_SEGMENT, target + CUT_WINDOW)
            if lo >= hi:
                continue
            y = lo + int(np.argmin(energy[lo:hi]))
            if float(energy[y]) > ENERGY_THRESHOLD:
                forced.append(y)
            cuts.append(y)
            prev = y
        out += list(pairwise([top, *cuts, bottom]))
    return out, forced


def detect(image: Image.Image) -> Detection:
    """One run's panels, gutters and forced cuts, in the run's own rows."""
    arr = np.asarray(image.convert("RGB"))
    raw_std = row_std(np.asarray(image.convert("L")))
    gutters = verified_gutters(arr)
    blocks = _glue_small(_blocks(arr.shape[0], gutters), arr.shape[1])
    blocks = [b for b in blocks if float(raw_std[b[0]:b[1]].max(initial=0)) > FEATURELESS_STD]
    panels, forced = auto_split(blocks, band_energy(raw_std), arr.shape[1])
    return Detection(panels, gutters, forced)
