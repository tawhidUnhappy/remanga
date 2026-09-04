"""Finding the gutter itself: the band of near-uniform background that
separates two panels.

This is the measurement layer - "is there a gutter near here, and where does
it start and end?" - with no notion of crop boxes at all. remanga.cropper.
gutter.refine is what turns those measurements into a moved edge."""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def _find_nearest_run(mask: np.ndarray, center_offset: int, min_run: int) -> Optional[Tuple[int, int]]:
    """Given a 1D boolean array (True = background/gutter) over a search window,
    returns the (start, end_exclusive) of the contiguous True run of length >=
    min_run closest to center_offset, or None if no such run exists.

    `center_offset` is the LLM's original coordinate expressed as an index into
    `mask` (mask[0] corresponds to the start of the search window).
    """
    n = len(mask)
    if n == 0:
        return None

    runs = []
    i = 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= min_run:
                runs.append((i, j))
            i = j
        else:
            i += 1

    if not runs:
        return None

    def distance(run: Tuple[int, int]) -> int:
        start, end = run
        if start <= center_offset < end:
            return 0
        return min(abs(start - center_offset), abs(end - 1 - center_offset))

    return min(runs, key=distance)


def locate_gutter_band(
    gray: np.ndarray,
    axis_len: int,
    center: int,
    perp_lo: int,
    perp_hi: int,
    along_rows: bool,
    bg: float,
    tolerance: float,
    search_radius: int,
    min_run: int,
    min_bg_fraction: float,
) -> Optional[int]:
    """Core search shared by single-edge refinement (below) and seam reconciliation
    (`remanga.cropper.seams`): looks for the background/gutter band nearest `center`
    within `search_radius` along one axis, scored over the perpendicular span
    [perp_lo, perp_hi). Returns the band's midpoint as an absolute coordinate, or
    None if no qualifying band exists nearby."""
    perp_lo = max(0, perp_lo)
    perp_hi = max(perp_lo + 1, perp_hi)
    if perp_hi - perp_lo < 1:
        return None

    lo = max(0, center - search_radius)
    hi = min(axis_len, center + search_radius + 1)
    if hi - lo < 2:
        return None

    if along_rows:
        strip = gray[lo:hi, perp_lo:perp_hi]
        fractions = np.mean(np.abs(strip - bg) <= tolerance, axis=1)
    else:
        strip = gray[perp_lo:perp_hi, lo:hi]
        fractions = np.mean(np.abs(strip - bg) <= tolerance, axis=0)

    is_bg = fractions >= min_bg_fraction
    run = _find_nearest_run(is_bg, center - lo, min_run)
    if run is None:
        return None

    start, end = run
    return int(lo + (start + end - 1) // 2)


