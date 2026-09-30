"""A long strip's panels, found without MAGI - ported from mangaEasy
(/mnt/datadisk/mangaEasy, mangaeasy/panels/gutter.py + webtoon.py, the user's
own project), where it is the production webtoon splitter.

MAGI was trained on printed pages: panels in a grid, words inside the borders.
A webtoon is one column read top to bottom, often borderless, with its bubbles
floating in the white between scenes - so MAGI's boxes cut bubbles in half and
box plain fades. A webtoon panel is instead a full-width band of the strip,
and the bands are separated by gutters: rows almost entirely one colour.

    gutter split   rows >= 97% one colour for >= 12 rows (one row >= 99.5%)
                   end a panel; tried for the strip's likely gutter colours
                   (white, black, the commonest row colours), best split wins,
                   then again inside every piece (a black scene inside a
                   white-gutter chapter)
    gap rescue     a dropped gap 40-700 rows tall with real content in it (a
                   caption, "ONE HOUR LATER...") joins the panel below it
    auto split     a panel taller than 2.2x the width is cut into ~1300-row
                   pieces at the quietest BAND near each even point - a
                   single quiet row is often the inside of a big bubble

All CPU numpy - mangaEasy's optional CUDA path is left out: a chapter runs
in seconds without it."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from PIL import Image

Range = tuple[int, int]

# mangaEasy's GutterConfig defaults.
GUTTER_SOLIDITY = 0.97
PERFECT_GUTTER = 0.995
MIN_GUTTER_HEIGHT = 12
COLOR_TOLERANCE = 8
MIN_PANEL_HEIGHT = 80
PADDING = 2
MAX_COLOR_SAMPLE_ROWS = 1000
MAX_WIDTH_SAMPLES = 650
CANDIDATE_COLORS = 8

# mangaEasy webtoon.py's "battle-tested defaults from production recap runs".
MAX_RATIO = 2.2
TARGET_HEIGHT = 1300
MIN_SEGMENT = 520
CUT_WINDOW = 380
ENERGY_THRESHOLD = 22.0
MIN_RESCUE_GAP = 40
MAX_RESCUE_GAP = 700


@dataclass(frozen=True)
class StripSplit:
    panels: list[Range]
    forced_cuts: list[int]  # auto-split rows that found no quiet band: cut through art


def _match_pct(arr: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    """Per row, the share of (sampled) pixels within tolerance of `color`."""
    stride = max(1, -(-arr.shape[1] // MAX_WIDTH_SAMPLES))
    sample = arr[:, ::stride, :].astype(np.int16, copy=False)
    return np.all(np.abs(sample - np.array(color, dtype=np.int16)) <= COLOR_TOLERANCE, axis=2).mean(axis=1)


def _split_from_match_pct(match_pct: np.ndarray) -> tuple[list[Range], int]:
    height = len(match_pct)
    solid = match_pct >= GUTTER_SOLIDITY
    raw: list[Range] = []
    in_panel, start, run, anchors = False, 0, 0, 0
    for y in range(height):
        if solid[y]:
            run += 1
            continue
        if run >= MIN_GUTTER_HEIGHT and in_panel:
            block = match_pct[y - run:y]
            perfect = int(np.sum(block >= PERFECT_GUTTER))
            if perfect:
                anchors += perfect
                if y - run - start >= MIN_PANEL_HEIGHT:
                    raw.append((start, y - run))
                in_panel = False
        run = 0
        if not in_panel:
            in_panel, start = True, y
    if in_panel and height - start >= MIN_PANEL_HEIGHT:
        raw.append((start, height))
    padded: list[Range] = []
    for top, bottom in raw:
        top, bottom = max(0, top - PADDING), min(height, bottom + PADDING)
        if padded:
            top = max(top, padded[-1][1])
        if bottom - top >= MIN_PANEL_HEIGHT:
            padded.append((top, bottom))
    return padded, len(padded) * 10000 + anchors


def _candidate_colors(arr: np.ndarray) -> list[tuple[int, int, int]]:
    rows = np.linspace(0, len(arr) - 1, num=min(len(arr), MAX_COLOR_SAMPLE_ROWS), dtype=int)
    counts = Counter(map(tuple, np.round(arr[rows].mean(axis=1)).astype(int).tolist()))
    common = [tuple(c) for c, _ in counts.most_common(CANDIDATE_COLORS)] or [(255, 255, 255)]
    whitest = min(common, key=lambda c: sum(255 - v for v in c))
    blackest = min(common, key=sum)
    picked = [whitest] if sum(255 - v for v in whitest) < 120 else []
    if sum(blackest) < 120 and blackest not in picked:
        picked.append(blackest)
    return picked + [c for c in common if c not in picked]


def gutter_ranges(arr: np.ndarray) -> list[Range]:
    """One level of the gutter split: the best split over the likely gutter
    colours (more panels wins, then more perfect gutter rows)."""
    if arr.shape[0] <= 1 or arr.shape[1] <= 1:
        return []
    best: list[Range] = []
    best_score = -1
    for color in _candidate_colors(arr):
        ranges, score = _split_from_match_pct(_match_pct(arr, color))
        if score > best_score:
            best, best_score = ranges, score
    return best


def recursive_ranges(arr: np.ndarray) -> list[Range]:
    """gutter_ranges, again inside every piece until nothing splits further."""
    queue = [(0, arr.shape[0])]
    finals: list[Range] = []
    while queue:
        off, end = queue.pop(0)
        ranges = gutter_ranges(arr[off:end])
        if len(ranges) > 1:
            queue = [(off + t, off + b) for t, b in ranges] + queue
        elif ranges:
            finals.append((off + ranges[0][0], off + ranges[0][1]))
        elif end - off >= MIN_PANEL_HEIGHT:
            finals.append((off, end))
    out: list[Range] = []
    for top, bottom in sorted(finals):
        if out:
            top = max(top, out[-1][1])
        if bottom - top >= MIN_PANEL_HEIGHT:
            out.append((top, bottom))
    return out


def row_std(gray: np.ndarray) -> np.ndarray:
    """Per-row 'busyness': the grey level's spread across the width (every
    third column, as mangaEasy measures it)."""
    return gray.astype(np.float32)[:, ::3].std(axis=1)


def rescue_gaps(ranges: list[Range], raw_std: np.ndarray) -> list[Range]:
    """A dropped gap holding real content (a caption between scenes) joins
    the panel below it, so no story text is lost."""
    out = list(ranges)
    gaps = [(0, out[0][0], 0)] + [(out[i][1], out[i + 1][0], i + 1) for i in range(len(out) - 1)] if out else []
    for top, bottom, below in gaps:
        if not MIN_RESCUE_GAP < bottom - top <= MAX_RESCUE_GAP:
            continue
        interior = raw_std[top + 15:bottom - 15]
        if interior.size and float(interior.max()) > ENERGY_THRESHOLD:
            out[below] = (top, out[below][1])
    return out


def band_energy(raw_std: np.ndarray, half_band: int = 24) -> np.ndarray:
    """Rolling max of row energy over +/-half_band rows: a cut is only safe in
    a band of quiet rows as wide as a real gutter."""
    if raw_std.size == 0:
        return raw_std
    padded = np.pad(raw_std, half_band, mode="edge")
    return np.lib.stride_tricks.sliding_window_view(padded, 2 * half_band + 1).max(axis=1)


def auto_split(ranges: list[Range], energy: np.ndarray, width: int) -> tuple[list[Range], list[int]]:
    """Panels taller than MAX_RATIO x width, cut near even points at the
    quietest band. Returns the ranges and the cuts that still went through
    art (no quiet band in the window)."""
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
        edges = [top, *cuts, bottom]
        out += list(pairwise(edges))
    return out, forced


def split_strip(image: Image.Image) -> StripSplit:
    """A stitched strip's panels, top to bottom, as [top, bottom) rows."""
    arr = np.asarray(image.convert("RGB"))
    raw_std = row_std(np.asarray(image.convert("L")))
    ranges = rescue_gaps(recursive_ranges(arr), raw_std)
    panels, forced = auto_split(ranges, band_energy(raw_std), arr.shape[1])
    return StripSplit([p for p in panels if not _featureless(p, raw_std)], forced)


# Not in mangaEasy (its reviewer deletes these by eye): a panel with no row
# busier than this is a plain fade between scenes or blank paper - every row
# one flat tone, the way a black-to-white fade is row by row. Measured: the
# fade in a real chapter came out as two "panels" with nothing to narrate.
FEATURELESS_STD = 4.0


def _featureless(panel: Range, raw_std: np.ndarray) -> bool:
    rows = raw_std[panel[0]:panel[1]]
    return not rows.size or float(rows.max()) <= FEATURELESS_STD
