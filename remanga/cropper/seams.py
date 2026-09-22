"""Cross-panel seam reconciliation - the second refinement pass that runs after
`remanga.cropper.gutter.refine_box_to_gutters` on every panel of a page.

Independent per-edge refinement can leave two supposedly-adjacent tiles disagreeing
about where their shared border actually is: one undershoots (leaving a strip of
its own content uncropped, which reads as a "gutter" gap) while the other
overshoots into that same strip (bleeding a slice of its neighbor's content into
its own crop). Both symptoms come from the same wrong seam, so this module fixes
them together instead of separately.
"""

from __future__ import annotations

import numpy as np

from remanga.cropper.gutter import PixelBox, locate_gutter_band


def _range_overlap_fraction(a0: float, a1: float, b0: float, b1: float) -> float:
    """What fraction of the *smaller* of two 1D ranges the overlap between them covers."""
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    smaller = min(a1 - a0, b1 - b0)
    return inter / smaller if smaller > 0 else 0.0


def _seam_search_radius(requested: int, center: int, a_lo: int, a_hi: int, b_lo: int, b_hi: int) -> int:
    """How far a joint seam search may look for the border between two panels,
    given where those two panels actually are along that axis.

    The requested radius is scaled to the PAGE (panel_boxes.adaptive_gutter_
    radius: a tenth of the longer side, 160px on a 1125x1600 scan), which is
    the right reach for two half-page tiles and far too much for a short one.
    On page 3 of chapter 1 it let the search for the border between the black
    caption banner (150px tall) and the art under it run 167px and find the
    white gutter ABOVE the banner instead: both facing edges were moved there,
    which left the banner as a 4px sliver of blank paper - and the panel went
    into the PDF blank, so the LLM marked it `skip: blank` (user report,
    2026-09-22).

    So the reach is also bounded by the panels themselves: the seam must leave
    at least half of each of them standing. A border found outside that window
    is not the border between these two panels, whatever it looks like. Zero
    means don't look at all - the two boxes overlap so heavily that no seam
    could leave both standing, and their marked edges are a better answer than
    anything this pass could find."""
    keep_a, keep_b = (a_hi - a_lo) // 2, (b_hi - b_lo) // 2
    lo, hi = a_lo + keep_a, b_hi - keep_b
    if lo >= hi:
        return 0
    return max(0, min(requested, center - lo, hi - center))


def reconcile_adjacent_seams(
    gray: np.ndarray,
    boxes: list[PixelBox],
    bg: float,
    search_radius: int = 120,
    tolerance: float = 20.0,
    min_run: int = 3,
    min_bg_fraction: float = 0.96,
    max_seam_gap_fraction: float = 0.15,
    min_axis_overlap_fraction: float = 0.5,
) -> list[PixelBox]:
    """Second pass over one page's already gutter-snapped panel boxes, in reading
    order. For every consecutive pair of boxes that looks like stacked or
    side-by-side tiles (their shared axis overlaps substantially and their facing
    edges are within a plausible gutter distance of each other, gap or overlap
    alike), this re-derives BOTH facing edges from a single joint gutter search
    centered between them, so they are geometrically guaranteed to agree - no gap,
    no overlap - instead of trusting two independent, possibly-inconsistent guesses.
    """
    boxes = list(boxes)
    h, w = gray.shape

    for i in range(len(boxes) - 1):
        l1, t1, r1, b1 = boxes[i]
        l2, t2, r2, b2 = boxes[i + 1]

        # Vertically stacked tiles: box i sits above box i+1, sharing a horizontal span.
        x_overlap = _range_overlap_fraction(l1, r1, l2, r2)
        gap = t2 - b1
        max_gap = int(h * max_seam_gap_fraction)
        if x_overlap >= min_axis_overlap_fraction and -search_radius <= gap <= max_gap:
            center = (b1 + t2) // 2
            radius = max(search_radius, abs(gap) // 2 + search_radius)
            radius = _seam_search_radius(radius, center, t1, b1, t2, b2)
            perp_lo, perp_hi = max(l1, l2), min(r1, r2)
            mid = locate_gutter_band(
                gray, h, center, perp_lo, perp_hi, True, bg, tolerance, radius, min_run, min_bg_fraction
            ) if radius > 0 else None
            if mid is not None and t1 < mid < b2:
                boxes[i] = (l1, t1, r1, mid)
                boxes[i + 1] = (l2, mid, r2, b2)
                continue

        # Horizontally adjacent tiles: box i left of box i+1, sharing a vertical span.
        y_overlap = _range_overlap_fraction(t1, b1, t2, b2)
        gap_x = l2 - r1
        max_gap_x = int(w * max_seam_gap_fraction)
        if y_overlap >= min_axis_overlap_fraction and -search_radius <= gap_x <= max_gap_x:
            center = (r1 + l2) // 2
            radius = max(search_radius, abs(gap_x) // 2 + search_radius)
            radius = _seam_search_radius(radius, center, l1, r1, l2, r2)
            perp_lo, perp_hi = max(t1, t2), min(b1, b2)
            mid = locate_gutter_band(
                gray, w, center, perp_lo, perp_hi, False, bg, tolerance, radius, min_run, min_bg_fraction
            ) if radius > 0 else None
            if mid is not None and l1 < mid < r2:
                boxes[i] = (l1, t1, mid, b1)
                boxes[i + 1] = (mid, t2, r2, b2)

    return boxes
