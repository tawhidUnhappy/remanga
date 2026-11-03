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

Split into the three things it does, in the order it does them:

    sampling.py - page -> grayscale, and what the background color is
    bands.py    - locating a gutter band near a given position
    refine.py   - snapping a crop box's edges onto those bands

Every name the cropper imported from the single module is re-exported here,
so `from remanga.cropper.gutter import ...` is unchanged for callers.
"""

from __future__ import annotations

from remanga.cropper.gutter.bands import locate_gutter_band
from remanga.cropper.gutter.refine import count_adjusted_edges, refine_box_to_gutters
from remanga.cropper.gutter.sampling import PixelBox, page_grayscale_array, sample_background_color

__all__ = [
    "PixelBox",
    "count_adjusted_edges",
    "locate_gutter_band",
    "page_grayscale_array",
    "refine_box_to_gutters",
    "sample_background_color",
]
