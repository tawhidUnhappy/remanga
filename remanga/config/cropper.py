"""Panel-cropping settings - see remanga/cropper/."""

from __future__ import annotations

from remanga.config.base import ConfigModel


class CropperConfig(ConfigModel):
    margin_padding_pixels: int = 8
    auto_contrast_clean: bool = False
    save_format: str = "PNG"

    # Gutter-snap refinement: treats the LLM's crops.json box as a best guess and
    # corrects each edge against real pixel evidence (see remanga/cropper/gutter/)
    # before margin_padding_pixels is applied. The actual search radius used per page
    # is adaptive: max(gutter_search_radius_pixels, page's longer side * fraction) -
    # a flat pixel floor undershoots badly on large scans when the LLM's guess is off
    # by more than a few dozen pixels, which is common enough to matter.
    snap_to_gutters: bool = True
    gutter_search_radius_pixels: int = 60         # floor: how far to look, even on small pages
    gutter_search_radius_fraction: float = 0.10   # scales the search radius with page size
    gutter_bg_tolerance: float = 20.0             # gray-level tolerance for "counts as background"
    gutter_min_run_pixels: int = 3                # minimum gutter band width to trust as real, not noise
    gutter_min_background_fraction: float = 0.96  # fraction of a row/col that must match bg to call it gutter

    # Seam reconciliation: a second pass over one page's already gutter-snapped
    # panels that re-derives shared borders between reading-order-adjacent tiles
    # jointly instead of independently, so neither panel can undershoot (a visible
    # gutter gap) while the other overshoots into it (bleeding the neighbor's tail
    # into its own crop) - both symptoms of one wrong seam. See
    # remanga/cropper/seams.py:reconcile_adjacent_seams.
    reconcile_panel_seams: bool = True
    # ignore pairs whose facing edges are this far apart (not really adjacent)
    seam_max_gap_fraction: float = 0.15
    # how much of the shared axis must overlap to count as "stacked/side-by-side"
    seam_min_axis_overlap_fraction: float = 0.5
    gutter_background_sample_strip_pixels: int = 12  # page-margin strip used to sample the background color

    # Final per-panel whitespace trim: after a panel is cropped (gutter-snapped,
    # seam-reconciled, and padded), trims any leftover thin band of pure background
    # still baked into the saved image - the last safety net for panels with no
    # neighbor to reconcile a seam against. See remanga/cropper/trim.py.
    trim_panel_whitespace: bool = True
    trim_min_background_fraction: float = 0.985   # stricter than gutter detection - only trims near-pure blank bands
    # never trims more than this fraction of a panel's width/height per side
    trim_max_margin_fraction: float = 0.04

    # Duplicate-crop safety net: drops any crops.json panel whose box is
    # near-identical in both position and size to an earlier one on the same
    # page (same frame marked twice), keeping the earlier crop. Deliberately
    # IoU-only - a small panel nested inside/heavily overlapping a much larger
    # one is a normal manga layout, not a duplicate, and must never be
    # silently dropped just because it sits mostly inside another panel's
    # box. See remanga/cropper/dedupe.py.
    dedupe_duplicate_panels: bool = True
    duplicate_iou_threshold: float = 0.6  # intersection-over-union that counts as a duplicate

    # Structured crops (remanga/cropper/structured.py - the LLM crop extension
    # writes them): paint other crops' frames and bubbles out of each crop's
    # rectangle, so no half bubble or sliver of the next panel rides along.
    # What exactly goes is remanga/cropper/paint_out.py. Marker-made panels
    # are never painted.
    paint_out: bool = True
