"""Classical computer-vision refinement for the crop boxes in `crops.json`.

Every box in `crops.json` comes from the Panel Marker web UI (remanga/webui/) -
either dragged out by hand or pre-filled by MAGI v3's detector and then left
as-is or nudged by hand - and either source is good at *finding* panels but
prone to being off by a few pixels at the actual edge: enough to slice a panel
border, a speech bubble, or leave a strip of the wrong panel in the crop.

This module treats the marked box as a best guess, not ground truth, and snaps
each of its four edges onto the real boundary it was aiming for: it looks for
the band of near-uniform background/paper color that separates panels (the
"gutter") near each marked edge, and centers the edge in the middle of that
band - the same thing a human would do eyeballing the gutter as a ruler, done
per pixel instead. If no confident gutter band exists near an edge
(frame-breaking bleed art, or the true physical edge of the page), that edge is
left untouched rather than forced to snap somewhere wrong.

See also: `remanga.cropper.seams` (a second pass that reconciles the shared edge
between two adjacent panels instead of refining each independently) and
`remanga.cropper.gutter_debug` (a standalone CLI for eyeballing one box's result).

Pure numpy + Pillow — no OpenCV dependency (kept intentionally lightweight since
this runs inline in the crop pipeline for every panel of every page).
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
from PIL import Image

PixelBox = Tuple[int, int, int, int]  # (left, top, right, bottom) - Pillow crop-box order


def page_grayscale_array(img: Image.Image) -> np.ndarray:
    """Converts a page image to a float32 grayscale array for gutter scoring."""
    return np.asarray(img.convert("L"), dtype=np.float32)


def sample_background_color(gray: np.ndarray, strip: int = 12) -> float:
    """Estimates the page's paper/background gray level from its outer margins,
    which are guaranteed to never fall inside a panel, so they're a safe reference
    for "what blank page/gutter looks like" on this particular scan."""
    h, w = gray.shape
    strip = max(1, min(strip, h // 4 or 1, w // 4 or 1))
    edges = np.concatenate([
        gray[:strip, :].ravel(),
        gray[-strip:, :].ravel(),
        gray[:, :strip].ravel(),
        gray[:, -strip:].ravel(),
    ])
    return float(np.median(edges))


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


def _max_radius_before_neighbor(
    coord: int,
    direction: int,
    perp_lo: int,
    perp_hi: int,
    other_boxes: Sequence[PixelBox],
    axis: str,
    requested_radius: int,
) -> int:
    """Shrinks `requested_radius` so an edge search can never walk into, or past,
    another panel's own already-known box - even one whose interior happens to
    read as background-colored (manga panels routinely have large blank/negative-
    space regions). Without this, a panel with a lot of internal whitespace can
    get mistaken for a gutter *through* it, and the searching edge snaps deep
    inside - or past - that neighbor instead of stopping at its actual border.

    `axis` is 'x' for a left/right edge search, 'y' for a top/bottom edge search.
    `direction` is +1 to search outward in the increasing direction (right or
    down), -1 for decreasing (left or up). Only a box whose perpendicular span
    overlaps [perp_lo, perp_hi) is even a candidate - a panel elsewhere on the
    page, outside this edge's own row/column band, can't be "in the way".

    The cap is applied unconditionally, even if `coord` already sits past the
    neighbor's near edge (a small overlap from ordinary marking imprecision,
    exactly what gutter-snap normally straightens out) - `max(0, ...)` at the
    end then floors that case to a radius of 0, i.e. this edge is left exactly
    where it was marked rather than refined at all. That's a deliberate
    fallback: better to leave a small, already-present overlap untouched than
    let the search keep looking and risk resolving to a spurious background run
    deeper inside (or past) the neighbor - which is the actual failure this
    function exists to prevent."""
    radius = requested_radius
    for (l, t, r, b) in other_boxes:
        other_lo, other_hi = (t, b) if axis == "x" else (l, r)
        if other_hi <= perp_lo or other_lo >= perp_hi:
            continue  # no perpendicular overlap - this box isn't in this edge's path

        near, far = (l, r) if axis == "x" else (t, b)
        if direction > 0:
            radius = min(radius, near - coord - 1)
        else:
            radius = min(radius, coord - far - 1)
    return max(0, radius)


def _refine_edge(
    gray: np.ndarray,
    axis_len: int,
    coord: int,
    perp_lo: int,
    perp_hi: int,
    along_rows: bool,
    bg: float,
    tolerance: float,
    search_radius: int,
    min_run: int,
    min_bg_fraction: float,
) -> int:
    """Refines one edge coordinate (a y for a horizontal edge, an x for a vertical
    edge) by snapping it to the middle of the nearest real gutter band found within
    `search_radius` pixels of the marked edge."""
    if coord <= 0 or coord >= axis_len:
        return coord  # true page edge - nothing to snap to, this is full bleed

    mid = locate_gutter_band(
        gray, axis_len, coord, perp_lo, perp_hi, along_rows, bg, tolerance, search_radius, min_run, min_bg_fraction
    )
    return coord if mid is None else mid


def refine_box_to_gutters(
    gray: np.ndarray,
    box: PixelBox,
    bg: float,
    other_boxes: Sequence[PixelBox] = (),
    search_radius: int = 40,
    tolerance: float = 20.0,
    min_run: int = 3,
    min_bg_fraction: float = 0.96,
) -> PixelBox:
    """Takes the marked pixel box and independently snaps each of its four edges
    to the true gutter band nearest to it, falling back to the original marked
    coordinate for any edge where no confident gutter band is found (e.g.
    frame-breaking character/speech-bubble bleed, or a genuine full-bleed page
    edge). Each edge is scored against the box's *original*, un-refined
    perpendicular span, so the four edges refine independently rather than
    compounding each other's corrections.

    `other_boxes` are every other panel already marked on this page (their
    original, un-refined boxes) - each edge's search radius is shrunk so it can
    never cross into one of them (see `_max_radius_before_neighbor`), which is
    what stops a low-content neighbor's own interior whitespace from ever being
    mistaken for a gutter running through - or past - it.
    """
    h, w = gray.shape
    left, top, right, bottom = box

    top_radius = _max_radius_before_neighbor(top, -1, left, right, other_boxes, "y", search_radius)
    bottom_radius = _max_radius_before_neighbor(bottom, 1, left, right, other_boxes, "y", search_radius)
    left_radius = _max_radius_before_neighbor(left, -1, top, bottom, other_boxes, "x", search_radius)
    right_radius = _max_radius_before_neighbor(right, 1, top, bottom, other_boxes, "x", search_radius)

    top_r = _refine_edge(gray, h, top, left, right, True, bg, tolerance, top_radius, min_run, min_bg_fraction)
    bottom_r = _refine_edge(gray, h, bottom, left, right, True, bg, tolerance, bottom_radius, min_run, min_bg_fraction)
    left_r = _refine_edge(gray, w, left, top, bottom, False, bg, tolerance, left_radius, min_run, min_bg_fraction)
    right_r = _refine_edge(gray, w, right, top, bottom, False, bg, tolerance, right_radius, min_run, min_bg_fraction)

    # Safety net: if a snap ever collapsed or inverted an axis (can happen in busy,
    # low-contrast art with no clean gutter), discard that axis's refinement and
    # keep the LLM's original coordinates rather than emit a broken box.
    if not (top_r < bottom_r):
        top_r, bottom_r = top, bottom
    if not (left_r < right_r):
        left_r, right_r = left, right

    return (left_r, top_r, right_r, bottom_r)


def count_adjusted_edges(original: PixelBox, refined: PixelBox, min_shift: int = 1) -> int:
    """How many of the 4 edges actually moved by at least `min_shift` px - used for
    the crop pipeline's summary line, not for any decision-making."""
    return sum(1 for a, b in zip(original, refined) if abs(a - b) >= min_shift)
