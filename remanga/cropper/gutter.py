"""Classical computer-vision refinement for LLM-guessed crop boxes.

The vision LLM that produces `crops.json` is good at *finding* panels but, per the
crop prompt's own "Pixel-Precision Mandate", is prone to eyeballing edges 20-40
units off on the 0-1000 scale — enough to slice a panel edge or a speech bubble.

This module treats the LLM's box as a best guess, not ground truth, and snaps each
of its four edges onto the real boundary it was aiming for: it looks for the band
of near-uniform background/paper color that separates panels (the "gutter") near
each guessed edge, and centers the edge in the middle of that band — exactly the
manual procedure the crop prompt asks a human to follow ("use the gutter as your
ruler"). If no confident gutter band exists near an edge (frame-breaking bleed art,
or the true physical edge of the page), that edge is left untouched rather than
forced to snap somewhere wrong.

Pure numpy + Pillow — no OpenCV dependency (kept intentionally lightweight since
this runs inline in the crop pipeline for every panel of every page).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

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


def _locate_gutter_band(
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
    """Core search shared by single-edge refinement and seam reconciliation: looks
    for the background/gutter band nearest `center` within `search_radius` along one
    axis, scored over the perpendicular span [perp_lo, perp_hi). Returns the band's
    midpoint as an absolute coordinate, or None if no qualifying band exists nearby."""
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
    `search_radius` pixels of the LLM's guess."""
    if coord <= 0 or coord >= axis_len:
        return coord  # true page edge - nothing to snap to, this is full bleed

    mid = _locate_gutter_band(
        gray, axis_len, coord, perp_lo, perp_hi, along_rows, bg, tolerance, search_radius, min_run, min_bg_fraction
    )
    return coord if mid is None else mid


def refine_box_to_gutters(
    gray: np.ndarray,
    box: PixelBox,
    bg: float,
    search_radius: int = 40,
    tolerance: float = 20.0,
    min_run: int = 3,
    min_bg_fraction: float = 0.96,
) -> PixelBox:
    """Takes the LLM's best-guess pixel box and independently snaps each of its
    four edges to the true gutter band nearest to it, falling back to the original
    LLM coordinate for any edge where no confident gutter band is found (e.g.
    frame-breaking character/speech-bubble bleed, or a genuine full-bleed page
    edge). Each edge is scored against the box's *original*, un-refined
    perpendicular span, so the four edges refine independently rather than
    compounding each other's corrections.
    """
    h, w = gray.shape
    left, top, right, bottom = box

    top_r = _refine_edge(gray, h, top, left, right, True, bg, tolerance, search_radius, min_run, min_bg_fraction)
    bottom_r = _refine_edge(gray, h, bottom, left, right, True, bg, tolerance, search_radius, min_run, min_bg_fraction)
    left_r = _refine_edge(gray, w, left, top, bottom, False, bg, tolerance, search_radius, min_run, min_bg_fraction)
    right_r = _refine_edge(gray, w, right, top, bottom, False, bg, tolerance, search_radius, min_run, min_bg_fraction)

    # Safety net: if a snap ever collapsed or inverted an axis (can happen in busy,
    # low-contrast art with no clean gutter), discard that axis's refinement and
    # keep the LLM's original coordinates rather than emit a broken box.
    if not (top_r < bottom_r):
        top_r, bottom_r = top, bottom
    if not (left_r < right_r):
        left_r, right_r = left, right

    return (left_r, top_r, right_r, bottom_r)


def _range_overlap_fraction(a0: float, a1: float, b0: float, b1: float) -> float:
    """What fraction of the *smaller* of two 1D ranges the overlap between them covers."""
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    smaller = min(a1 - a0, b1 - b0)
    return inter / smaller if smaller > 0 else 0.0


def reconcile_adjacent_seams(
    gray: np.ndarray,
    boxes: List[PixelBox],
    bg: float,
    search_radius: int = 120,
    tolerance: float = 20.0,
    min_run: int = 3,
    min_bg_fraction: float = 0.96,
    max_seam_gap_fraction: float = 0.15,
    min_axis_overlap_fraction: float = 0.5,
) -> List[PixelBox]:
    """Second pass over one page's already gutter-snapped panel boxes, in reading
    order. Independent per-edge refinement (refine_box_to_gutters) can leave two
    supposedly-adjacent tiles disagreeing about where their shared border actually
    is - one undershoots (leaving a strip of its own content uncropped, which reads
    as a "gutter" gap) while the other overshoots into that same strip (bleeding a
    slice of its neighbor's content into its own crop). Both symptoms come from the
    same wrong seam.

    For every consecutive pair of boxes that looks like stacked or side-by-side
    tiles (their shared axis overlaps substantially and their facing edges are
    within a plausible gutter distance of each other, gap or overlap alike), this
    re-derives BOTH facing edges from a single joint gutter search centered between
    them, so they are geometrically guaranteed to agree - no gap, no overlap -
    instead of trusting two independent, possibly-inconsistent guesses.
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
            perp_lo, perp_hi = max(l1, l2), min(r1, r2)
            mid = _locate_gutter_band(gray, h, center, perp_lo, perp_hi, True, bg, tolerance, radius, min_run, min_bg_fraction)
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
            perp_lo, perp_hi = max(t1, t2), min(b1, b2)
            mid = _locate_gutter_band(gray, w, center, perp_lo, perp_hi, False, bg, tolerance, radius, min_run, min_bg_fraction)
            if mid is not None and l1 < mid < r2:
                boxes[i] = (l1, t1, mid, b1)
                boxes[i + 1] = (mid, t2, r2, b2)

    return boxes


def count_adjusted_edges(original: PixelBox, refined: PixelBox, min_shift: int = 1) -> int:
    """How many of the 4 edges actually moved by at least `min_shift` px - used for
    the crop pipeline's summary line, not for any decision-making."""
    return sum(1 for a, b in zip(original, refined) if abs(a - b) >= min_shift)


def _debug_visualize(page_path: str, box: PixelBox, refined: PixelBox, out_path: str) -> None:
    """Draws the LLM's original box (red) and the gutter-refined box (green) over
    the page for visual sanity-checking. Debug/manual-use only - not called by the
    production pipeline."""
    img = Image.open(page_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle(box, outline=(255, 0, 0), width=3)
    draw.rectangle(refined, outline=(0, 200, 0), width=3)
    img.save(out_path)


def _main() -> None:
    """Standalone CLI for eyeballing the gutter-snap on one panel of one page:

        python -m remanga.cropper.gutter <page_image> <ymin> <xmin> <ymax> <xmax> [out_debug.png]

    Coordinates are in the same normalized 0-1000 scale crops.json uses.
    """
    import sys

    from remanga.cropper.geometry import calculate_pixel_bounds

    if len(sys.argv) < 6:
        print(__doc__)
        print(_main.__doc__)
        raise SystemExit(1)

    page_path = sys.argv[1]
    ymin, xmin, ymax, xmax = (int(v) for v in sys.argv[2:6])
    out_path = sys.argv[6] if len(sys.argv) > 6 else "gutter_debug.png"

    img = Image.open(page_path)
    img_w, img_h = img.size
    gray = page_grayscale_array(img)
    bg = sample_background_color(gray)

    original_box = calculate_pixel_bounds([ymin, xmin, ymax, xmax], img_w, img_h, is_1000=True)
    refined_box = refine_box_to_gutters(gray, original_box, bg)

    print(f"Page background level (0-255): {bg:.1f}")
    print(f"LLM guess (pixels, L/T/R/B):     {original_box}")
    print(f"Gutter-refined (pixels, L/T/R/B): {refined_box}")
    print(f"Edges adjusted: {count_adjusted_edges(original_box, refined_box)}/4")

    _debug_visualize(page_path, original_box, refined_box, out_path)
    print(f"Debug overlay (red=LLM guess, green=refined) saved to: {out_path}")


if __name__ == "__main__":
    _main()
