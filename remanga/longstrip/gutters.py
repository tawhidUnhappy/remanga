"""Where a long strip's gutters are - found, and then verified before any of
them is allowed to cut.

mangaEasy's splitter (the first port) guessed a gutter colour again inside
every piece it had already cut and kept whichever guess gave the MOST panels:
on a real chapter it tried 425 colours, and a guess taken from inside a panel
(a flat sky, a plain background) cut that panel in two. Here a colour has to
prove itself on the strip first:

1. a row is SOLID when nearly all of it is one colour (its median, within
   COLOR_TOLERANCE per channel) - a fade is solid row by row, but its colour
   drifts, so it breaks into runs too short to be gutters;
2. a run of solid rows of one colour, at least MIN_GUTTER_ROWS tall and with
   one row that is PERFECT, is a candidate gutter;
3. candidates are grouped by colour, and a candidate is a gutter when its
   colour separates the strip at least STRONG_REPEATS times over the chapter
   ("strong" - white or black gutters) or at least LOCAL_REPEATS times within
   LOCAL_WINDOW rows around it ("local" - a flashback in black, a scene in pink,
   with gutters of its own colour). A one-off flat patch is neither and never
   cuts.

Webtoons use more than one gutter colour, so there is no single "the gutter
colour": every colour that verifies is used, each where it verifies. All numpy,
one pass over the pixels: ~1 s for a 90,000-row chapter where the guessing
took 15."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

COLOR_TOLERANCE = 8        # per channel, as mangaEasy
SOLID_SHARE = 0.97         # of the row within tolerance of its median
PERFECT_SHARE = 0.995
MIN_GUTTER_ROWS = 12
MAX_WIDTH_SAMPLES = 650    # columns looked at per row
SAME_COLOR = 16            # max per-channel difference to count as one colour
STRONG_REPEATS = 3
LOCAL_REPEATS = 2
LOCAL_WINDOW = 6000        # rows either side


@dataclass(frozen=True)
class Gutter:
    top: int
    bottom: int
    color: tuple[int, int, int]
    strength: str          # "strong" | "local"


def row_colors(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each row's median colour and the share of it within tolerance of that."""
    stride = max(1, -(-arr.shape[1] // MAX_WIDTH_SAMPLES))
    sample = arr[:, ::stride, :]
    mid = sample.shape[1] // 2
    median = np.partition(sample, mid, axis=1)[:, mid, :].astype(np.int16)
    close = np.abs(sample.astype(np.int16) - median[:, None, :]) <= COLOR_TOLERANCE
    return median, close.all(axis=2).mean(axis=1)


def candidate_runs(median: np.ndarray, share: np.ndarray) -> list[tuple[int, int, tuple[int, int, int]]]:
    """Runs of solid rows of one colour that could be gutters: (top, bottom, colour)."""
    solid = share >= SOLID_SHARE
    runs = []
    start = None
    for y in range(len(share) + 1):
        if start is not None and (y == len(share) or not solid[y]
                                  or np.abs(median[y] - median[start]).max() > COLOR_TOLERANCE):
            if y - start >= MIN_GUTTER_ROWS and share[start:y].max() >= PERFECT_SHARE:
                color = tuple(int(c) for c in np.median(median[start:y], axis=0))
                runs.append((start, y, color))
            start = None
        if start is None and y < len(share) and solid[y]:
            start = y
    return runs


def group_of(color, groups: list[tuple[int, int, int]]) -> int:
    for i, known in enumerate(groups):
        if max(abs(a - b) for a, b in zip(color, known, strict=True)) <= SAME_COLOR:
            return i
    groups.append(color)
    return len(groups) - 1


def verified_gutters(arr: np.ndarray) -> list[Gutter]:
    """The strip's gutters, each verified by its own colour's repeats - see
    the module doc. Runs at the very top or bottom are margins, not gutters
    between panels, and are left out."""
    height = arr.shape[0]
    median, share = row_colors(arr)
    runs = [r for r in candidate_runs(median, share) if r[0] > 0 and r[1] < height]
    colors: list[tuple[int, int, int]] = []
    group = [group_of(color, colors) for _, _, color in runs]
    # A repeat only counts with art between the two: the steps of one fade
    # are solid runs of neighbouring colours with nothing but more fade
    # between them, and measured on a real chapter they "verified" each
    # other as six gutters.
    art_before = np.concatenate(([0], np.cumsum(share < SOLID_SHARE)))

    def separate(i: int, j: int) -> bool:
        (_, first_bottom, _), (second_top, _, _) = sorted((runs[i], runs[j]))
        return art_before[second_top] - art_before[first_bottom] > 0

    gutters = []
    for i, (top, bottom, color) in enumerate(runs):
        same = [j for j in range(len(runs)) if group[j] == group[i]]
        repeats = [j for j in same if j == i or separate(i, j)]
        if len(repeats) >= STRONG_REPEATS:
            strength = "strong"
        elif sum(1 for j in repeats if abs(runs[j][0] - top) <= LOCAL_WINDOW) >= LOCAL_REPEATS:
            strength = "local"
        else:
            continue
        gutters.append(Gutter(top, bottom, color, strength))
    return gutters
