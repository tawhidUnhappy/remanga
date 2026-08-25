"""Per-page cropping: locates one page's image, resolves its panel boxes, and
crops/trims/saves each panel. Split out of crop.py so CoordinateCropper stays
a thin per-chapter loop over this one function."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageOps

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.dedupe import dedupe_panels
from remanga.cropper.geometry import apply_padding
from remanga.cropper.gutter import count_adjusted_edges, page_grayscale_array, sample_background_color
from remanga.cropper.page_locator import locate_page_file
from remanga.cropper.panel_boxes import resolve_page_panel_boxes
from remanga.cropper.trim import trim_panel_margins


@dataclass
class PageCropResult:
    """Everything one page's worth of cropping produced, so the chapter-level
    loop in crop.py only has to accumulate these, not track loose counters."""

    panel_paths: List[Path] = field(default_factory=list)
    manifest_entries: List[Dict[str, Any]] = field(default_factory=list)
    next_panel_counter: int = 1
    gutter_panels_adjusted: int = 0
    gutter_edges_adjusted: int = 0
    duplicate_panels_dropped: int = 0
    panels_trimmed: int = 0


def crop_page(
    page_entry: Dict[str, Any],
    pages_dir: Path,
    panels_dir: Path,
    panel_counter: int,
    config: CropperConfig,
) -> Optional[PageCropResult]:
    """Crops every panel on one crops.json page entry. Returns None if the
    page was skipped (not a story page, no panels, or its image couldn't be
    located) - the caller just moves on to the next page_entry in that case."""
    is_story_page = page_entry.get("is_story_page", True)
    panels = page_entry.get("panels", [])

    if not is_story_page or not panels:
        page_desc = page_entry.get("page_filename") or f"page index {page_entry.get('page_index')}"
        note_str = page_entry.get("notes", "non-story/duplicate")
        console.print(f"[dim yellow]Skipping non-story page ({page_desc}): {note_str}[/]")
        return None

    result = PageCropResult(next_panel_counter=panel_counter)

    # Safety net for crop-prompt Rule 8: drop any panel entry whose box is a
    # duplicate/near-duplicate of an earlier one on this page (same bordered
    # frame re-cropped twice), keeping the earliest occurrence per reading
    # order. A recurring character across genuinely distinct, non-overlapping
    # panel boxes is untouched - see remanga/cropper/dedupe.py.
    if config.dedupe_duplicate_panels:
        page_desc = page_entry.get("page_filename") or f"page index {page_entry.get('page_index')}"
        panels, dupe_report = dedupe_panels(
            panels,
            iou_threshold=config.duplicate_iou_threshold,
            containment_threshold=config.duplicate_containment_threshold,
        )
        result.duplicate_panels_dropped = len(dupe_report)
        for dupe in dupe_report:
            console.print(
                f"[bold yellow]⚠ Duplicate crop dropped on {page_desc}:[/] "
                f"panel_id {dupe['dropped_panel_id']!r} overlaps panel_id {dupe['kept_panel_id']!r} "
                f"(IoU {dupe['iou']:.2f}, containment {dupe['containment']:.2f}) - keeping the earlier crop."
            )

    page_filename = page_entry.get("page_filename")
    page_index = page_entry.get("page_index")

    page_img_path = locate_page_file(pages_dir, page_filename, page_index)
    if not page_img_path or not page_img_path.exists():
        console.print(f"[yellow]Warning: Could not locate page image for: {page_entry}. Skipping...[/]")
        return None

    with Image.open(page_img_path) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img_w, img_h = img.size

        # Computed once per page (not per panel) and reused by panel box
        # resolution below (remanga/cropper/panel_boxes.py) and by the final
        # per-panel trim (remanga/cropper/trim.py).
        needs_page_analysis = config.snap_to_gutters or config.trim_panel_whitespace
        gray_arr = page_grayscale_array(img) if needs_page_analysis else None
        bg_level = (
            sample_background_color(gray_arr, config.gutter_background_sample_strip_pixels)
            if gray_arr is not None else None
        )

        valid_panels, original_boxes, panel_boxes = resolve_page_panel_boxes(
            panels, img_w, img_h, gray_arr, bg_level, config
        )

        for panel, original_box, crop_box in zip(valid_panels, original_boxes, panel_boxes):
            if config.snap_to_gutters:
                adjusted = count_adjusted_edges(original_box, crop_box)
                if adjusted:
                    result.gutter_panels_adjusted += 1
                    result.gutter_edges_adjusted += adjusted

            if config.margin_padding_pixels > 0:
                crop_box = apply_padding(crop_box, img_w, img_h, config.margin_padding_pixels)

            cropped_img = img.crop(crop_box)

            # Last safety net: trim any leftover blank margin still baked into
            # the saved image (e.g. a panel with no neighbor to reconcile a
            # seam against) - see remanga/cropper/trim.py.
            if config.trim_panel_whitespace and bg_level is not None:
                cl, ct, cr, cb = crop_box
                cropped_img, (tl, tt, tr, tb) = trim_panel_margins(
                    cropped_img, bg_level,
                    tolerance=config.gutter_bg_tolerance,
                    min_bg_fraction=config.trim_min_background_fraction,
                    max_trim_fraction=config.trim_max_margin_fraction,
                )
                if (tl, tt, tr, tb) != (0, 0, cr - cl, cb - ct):
                    result.panels_trimmed += 1
                    # Keep crop_box's provenance (recorded below) accurate:
                    # translate the trim's local box back onto the page.
                    crop_box = (cl + tl, ct + tt, cl + tr, ct + tb)

            if config.auto_contrast_clean:
                cropped_img = ImageOps.autocontrast(cropped_img, cutoff=1)

            out_name = f"panel_{result.next_panel_counter:03d}.{config.save_format.lower()}"
            out_path = panels_dir / out_name
            cropped_img.save(out_path, format=config.save_format, quality=95)
            result.panel_paths.append(out_path)

            result.manifest_entries.append({
                "panel_id": f"panel_{result.next_panel_counter:03d}",
                "source_page": page_img_path.name,
                "crop_bounds": list(crop_box),
                "width": cropped_img.width,
                "height": cropped_img.height,
                "aspect_ratio": round(cropped_img.width / cropped_img.height, 4),
                "type": panel.get("type", "standard"),
                "notes": panel.get("notes", ""),
            })

            result.next_panel_counter += 1

    return result
