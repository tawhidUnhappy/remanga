"""One page's crops cut the way `crop` saves them - boxes resolved (gutter-
snapped, or planned as structured crops), padded, neighbours painted out,
blank margin trimmed. The one definition of a finished crop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from remanga.config import CropperConfig
from remanga.cropper.geometry import apply_padding
from remanga.cropper.gutter import count_adjusted_edges, page_grayscale_array, sample_background_color
from remanga.cropper.panel_boxes import resolve_page_panel_boxes
from remanga.cropper.structured import CropPlan, has_structured_crops, paint_mask, plan_structured_crops
from remanga.cropper.trim import trim_panel_margins


@dataclass
class CutCrop:
    """One crop exactly as `crop` saves it, and how it got there."""

    image: Image.Image
    box: tuple[int, int, int, int]  # where it came from on the page, after padding and trim
    adjusted_edges: int = 0
    painted: bool = False
    trimmed: bool = False


def cut_crops(img: Image.Image, panels: list[dict[str, Any]], config: CropperConfig) -> list[CutCrop]:
    """Every crop of one RGB page image, in order, cut the way `crop` cuts
    them: boxes resolved (gutter-snapped, or planned as structured crops),
    padded, neighbours painted out, blank margin trimmed. The one definition
    of a finished crop - crop_page saves these, and the LLM crop previews
    show them, so a preview can't show anything the cut won't produce."""
    img_w, img_h = img.size
    structured = has_structured_crops(panels)
    painting = structured and config.paint_out

    # Computed once per page (not per panel) and reused by panel box
    # resolution below (remanga/cropper/panel_boxes.py), by the final
    # per-panel trim (remanga/cropper/trim.py), and as the paper colour
    # a structured crop's neighbours are painted over with.
    needs_page_analysis = config.snap_to_gutters or config.trim_panel_whitespace or painting
    gray_arr = page_grayscale_array(img) if needs_page_analysis else None
    bg_level = (
        sample_background_color(gray_arr, config.gutter_background_sample_strip_pixels)
        if gray_arr is not None else None
    )

    if structured:
        plans = plan_structured_crops(panels, img_w, img_h, gray_arr, bg_level, config)
    else:
        _valid_panels, original_boxes, panel_boxes = resolve_page_panel_boxes(
            panels, img_w, img_h, gray_arr, bg_level, config
        )
        plans = [CropPlan(marked=[original], frames=[refined])
                 for original, refined in zip(original_boxes, panel_boxes, strict=True)]

    cuts: list[CutCrop] = []
    for index, plan in enumerate(plans):
        adjusted = 0
        if config.snap_to_gutters:
            adjusted = sum(count_adjusted_edges(original, refined)
                           for original, refined in zip(plan.marked, plan.frames, strict=True))

        crop_box = plan.rect
        if config.margin_padding_pixels > 0:
            crop_box = apply_padding(crop_box, img_w, img_h, config.margin_padding_pixels)

        cropped_img = img.crop(crop_box)

        painted = False
        if painting and bg_level is not None:
            paint = paint_mask(plans, index, crop_box)
            if paint is not None:
                pixels = np.array(cropped_img)
                pixels[paint] = round(bg_level)
                cropped_img = Image.fromarray(pixels)
                painted = True

        # Last safety net: trim any leftover blank margin still baked into
        # the saved image (e.g. a panel with no neighbor to reconcile a
        # seam against) - see remanga/cropper/trim.py.
        trimmed = False
        if config.trim_panel_whitespace and bg_level is not None:
            cl, ct, cr, cb = crop_box
            cropped_img, (tl, tt, tr, tb) = trim_panel_margins(
                cropped_img, bg_level,
                tolerance=config.gutter_bg_tolerance,
                min_bg_fraction=config.trim_min_background_fraction,
                max_trim_fraction=config.trim_max_margin_fraction,
            )
            if (tl, tt, tr, tb) != (0, 0, cr - cl, cb - ct):
                trimmed = True
                crop_box = (cl + tl, ct + tt, cl + tr, ct + tb)

        if config.auto_contrast_clean:
            cropped_img = ImageOps.autocontrast(cropped_img, cutoff=1)

        cuts.append(CutCrop(cropped_img, crop_box, adjusted, painted, trimmed))
    return cuts
