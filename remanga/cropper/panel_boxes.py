"""Per-page panel box resolution: turns crops.json's marked boxes into final,
gutter-snapped and seam-reconciled pixel crop boxes for one page, before any
cropping or saving happens.

Two passes, both optional/config-gated:
1. Gutter-snap every panel's box, aware of every other panel's box on the page
   so a search can't wander into one (remanga.cropper.gutter).
2. Reconcile the shared edge between reading-order-adjacent panels so neither
   undershoots nor overshoots into the other (remanga.cropper.seams).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.cropper.geometry import calculate_pixel_bounds
from remanga.cropper.gutter import PixelBox, refine_box_to_gutters
from remanga.cropper.seams import reconcile_adjacent_seams


def adaptive_gutter_radius(config: CropperConfig, img_w: int, img_h: int) -> int:
    """A flat pixel radius undershoots on large scans; scale it with the page's
    longer side so a big marking error is still reachable."""
    return max(
        config.gutter_search_radius_pixels,
        round(max(img_w, img_h) * config.gutter_search_radius_fraction),
    )


def resolve_page_panel_boxes(
    panels: List[Dict[str, Any]],
    img_w: int,
    img_h: int,
    gray_arr: Optional[np.ndarray],
    bg_level: Optional[float],
    config: CropperConfig,
) -> Tuple[List[Dict[str, Any]], List[PixelBox], List[PixelBox]]:
    """Returns (valid_panels, original_boxes, refined_boxes) - three parallel
    lists, one entry per panel with valid coordinates (invalid entries are
    skipped and logged). `refined_boxes` have been through gutter-snap and, if
    enabled, seam reconciliation; `original_boxes` are the marked, un-refined
    boxes, kept around so refine_box_to_gutters can clamp against them and so
    the caller can report how much correction happened."""
    do_gutter_snap = gray_arr is not None and config.snap_to_gutters
    gutter_radius = adaptive_gutter_radius(config, img_w, img_h) if do_gutter_snap else 0

    valid_panels: List[Dict[str, Any]] = []
    original_boxes: List[PixelBox] = []

    # First pass: resolve every panel's original marked box up front, before any
    # snapping - refine_box_to_gutters (below) needs every OTHER panel's box
    # already known so it can clamp its own search and never cross into one.
    for panel in panels:
        box = panel.get("box_1000") or panel.get("box_pixel") or panel.get("coordinates")
        if not box or len(box) != 4:
            console.print(f"[yellow]Skipping invalid panel coordinate entry: {_esc(str(panel))}[/]")
            continue

        is_normalized = "box_1000" in panel or max(box) <= 1000
        valid_panels.append(panel)
        original_boxes.append(calculate_pixel_bounds(box, img_w, img_h, is_1000=is_normalized))

    panel_boxes: List[PixelBox] = []
    for idx, original_box in enumerate(original_boxes):
        crop_box = original_box

        # Treat the marked box as a best guess: snap each edge onto the real
        # gutter/panel border nearest to it before the caller applies safety
        # padding. other_boxes = every other panel on this page, so the search
        # for THIS panel's edges can never wander into one of them.
        if do_gutter_snap:
            other_boxes = original_boxes[:idx] + original_boxes[idx + 1:]
            crop_box = refine_box_to_gutters(
                gray_arr, crop_box, bg_level,
                other_boxes=other_boxes,
                search_radius=gutter_radius,
                tolerance=config.gutter_bg_tolerance,
                min_run=config.gutter_min_run_pixels,
                min_bg_fraction=config.gutter_min_background_fraction,
            )

        panel_boxes.append(crop_box)

    # Reconcile shared borders between reading-order-adjacent panels so neither
    # undershoots (a visible gutter gap) while the other overshoots into it
    # (bleeding the neighbor's content into its own crop).
    if do_gutter_snap and config.reconcile_panel_seams and len(panel_boxes) > 1:
        panel_boxes = reconcile_adjacent_seams(
            gray_arr, panel_boxes, bg_level,
            search_radius=gutter_radius,
            tolerance=config.gutter_bg_tolerance,
            min_run=config.gutter_min_run_pixels,
            min_bg_fraction=config.gutter_min_background_fraction,
            max_seam_gap_fraction=config.seam_max_gap_fraction,
            min_axis_overlap_fraction=config.seam_min_axis_overlap_fraction,
        )

    return valid_panels, original_boxes, panel_boxes
