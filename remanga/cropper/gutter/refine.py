"""Turning gutter measurements into snapped crop-box edges.

Each of a box's four edges is considered independently: look for a
confident gutter band near it, and center the edge in that band. An edge
with no confident band nearby (frame-breaking bleed art, or the true
physical page edge) is left exactly where the marker put it - refusing to
move is a valid, and frequently correct, answer here."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from remanga.cropper.gutter.bands import locate_gutter_band
from remanga.cropper.gutter.sampling import PixelBox


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
    for left, top, right, bottom in other_boxes:
        other_lo, other_hi = (top, bottom) if axis == "x" else (left, right)
        if other_hi <= perp_lo or other_lo >= perp_hi:
            continue  # no perpendicular overlap - this box isn't in this edge's path

        near, far = (left, right) if axis == "x" else (top, bottom)
        radius = min(radius, near - coord - 1) if direction > 0 else min(radius, coord - far - 1)
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

    It is shrunk once more, by the box's own size: no edge may search past the
    middle of the panel it belongs to. The radius comes in scaled to the page
    (panel_boxes.adaptive_gutter_radius - 160px on a 1125x1600 scan), which is
    a reasonable marking error on a half-page tile and more than the whole of a
    caption strip or a narrow sliver of a panel. Without this bound, a short
    panel's two facing edges can both reach the same band and meet in the
    middle, and the only thing standing between that and a crop of blank paper
    is the inversion check below - which a band a few pixels wide passes.
    """
    h, w = gray.shape
    left, top, right, bottom = box
    half_h, half_w = (bottom - top) // 2, (right - left) // 2

    top_radius = _max_radius_before_neighbor(top, -1, left, right, other_boxes, "y", search_radius)
    bottom_radius = _max_radius_before_neighbor(bottom, 1, left, right, other_boxes, "y", search_radius)
    left_radius = _max_radius_before_neighbor(left, -1, top, bottom, other_boxes, "x", search_radius)
    right_radius = _max_radius_before_neighbor(right, 1, top, bottom, other_boxes, "x", search_radius)
    top_radius, bottom_radius = min(top_radius, half_h), min(bottom_radius, half_h)
    left_radius, right_radius = min(left_radius, half_w), min(right_radius, half_w)

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
    return sum(1 for a, b in zip(original, refined, strict=True) if abs(a - b) >= min_shift)
