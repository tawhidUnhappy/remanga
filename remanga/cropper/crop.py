"""Chapter-level crop orchestration: reads crops.json, resolves and crops every
panel, then packages the vision upload archive. The actual box math lives in
remanga.cropper.panel_boxes/gutter/seams/dedupe - this module just wires the
pipeline stages together in order."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageOps
from rich.console import Console

from remanga.config import CropperConfig
from remanga.cropper.archive import create_vision_archive
from remanga.cropper.dedupe import dedupe_panels
from remanga.cropper.geometry import apply_padding
from remanga.cropper.gutter import count_adjusted_edges, page_grayscale_array, sample_background_color
from remanga.cropper.page_locator import locate_page_file
from remanga.cropper.panel_boxes import resolve_page_panel_boxes
from remanga.cropper.sheets import PanelSheetGenerator
from remanga.json_io import read_json, write_json
from remanga.paths import get_chapter_dir

console = Console()


class CoordinateCropper:
    def __init__(self, config: Optional[CropperConfig] = None):
        self.config = config or CropperConfig()

    def crop_chapter_from_json(self, project_name: str, chapter_num: str, force: bool = False) -> List[Path]:
        """
        Reads crops.json in the chapter directory, crops panels, generates
        contact sheets or panel archives, and packages according to config.
        Skips if already cropped and force is False.
        """
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        crops_json_path = chapter_dir / "crops.json"
        pages_dir = chapter_dir / "pages"
        panels_dir = chapter_dir / "panels"
        sheets_dir = chapter_dir / "sheets"
        manifest_path = chapter_dir / "panels_manifest.json"

        asset_type = getattr(self.config, "vision_asset_type", "sheets").lower()
        expected_zip = chapter_dir / ("panels.zip" if asset_type == "panels" else "sheets.zip")

        if not crops_json_path.exists() or crops_json_path.stat().st_size <= 10:
            raise FileNotFoundError(
                f"Missing or empty crop instructions file: {crops_json_path}\n"
                f"Please paste your LLM-generated JSON into this placeholder file."
            )

        if not pages_dir.exists() or not list(pages_dir.glob("page_*.*")):
            raise FileNotFoundError(
                f"Pages directory is empty: {pages_dir}\n"
                f"Please download the chapter pages first."
            )

        # RESUME CHECK: If panels already exist and force=False, verify and skip
        existing_panels = sorted(list(panels_dir.glob("panel_*.*")))
        if not force and existing_panels and manifest_path.exists() and expected_zip.exists():
            console.print(f"[bold green]✓ Found {len(existing_panels)} panels already cropped and {expected_zip.name} ready! Skipping re-crop.[/]")
            return existing_panels

        # Clear existing panels directory before fresh cropping
        panels_dir.mkdir(parents=True, exist_ok=True)
        for old_file in list(panels_dir.glob("panel_*.*")):
            try:
                old_file.unlink()
            except Exception:
                pass

        crop_data = read_json(crops_json_path)

        pages_list = crop_data.get("pages", [])
        if not pages_list:
            raise ValueError(f"Invalid crops.json: No 'pages' array found in {crops_json_path}")

        console.print(f"[cyan]Processing panel cropping for chapter {chapter_num}...[/]")

        panel_counter = 1
        output_panel_paths: List[Path] = []
        manifest_data: List[Dict[str, Any]] = []
        gutter_panels_adjusted = 0
        gutter_edges_adjusted = 0
        duplicate_panels_dropped = 0

        for page_entry in pages_list:
            is_story_page = page_entry.get("is_story_page", True)
            panels = page_entry.get("panels", [])

            if not is_story_page or not panels:
                page_desc = page_entry.get("page_filename") or f"page index {page_entry.get('page_index')}"
                note_str = page_entry.get("notes", "non-story/duplicate")
                console.print(f"[dim yellow]Skipping non-story page ({page_desc}): {note_str}[/]")
                continue

            # Safety net for crop-prompt Rule 8: drop any panel entry whose box is a
            # duplicate/near-duplicate of an earlier one on this page (same bordered
            # frame re-cropped twice), keeping the earliest occurrence per reading
            # order. A recurring character across genuinely distinct, non-overlapping
            # panel boxes is untouched - see remanga/cropper/dedupe.py.
            if self.config.dedupe_duplicate_panels:
                page_desc = page_entry.get("page_filename") or f"page index {page_entry.get('page_index')}"
                panels, dupe_report = dedupe_panels(
                    panels,
                    iou_threshold=self.config.duplicate_iou_threshold,
                    containment_threshold=self.config.duplicate_containment_threshold,
                )
                for dupe in dupe_report:
                    duplicate_panels_dropped += 1
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
                continue

            with Image.open(page_img_path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
                img_w, img_h = img.size

                # Computed once per page (not per panel) and reused by panel box
                # resolution below - see remanga/cropper/panel_boxes.py.
                gray_arr = page_grayscale_array(img) if self.config.snap_to_gutters else None
                bg_level = (
                    sample_background_color(gray_arr, self.config.gutter_background_sample_strip_pixels)
                    if gray_arr is not None else None
                )

                valid_panels, original_boxes, panel_boxes = resolve_page_panel_boxes(
                    panels, img_w, img_h, gray_arr, bg_level, self.config
                )

                for panel, original_box, crop_box in zip(valid_panels, original_boxes, panel_boxes):
                    if gray_arr is not None:
                        adjusted = count_adjusted_edges(original_box, crop_box)
                        if adjusted:
                            gutter_panels_adjusted += 1
                            gutter_edges_adjusted += adjusted

                    if self.config.margin_padding_pixels > 0:
                        crop_box = apply_padding(crop_box, img_w, img_h, self.config.margin_padding_pixels)

                    cropped_img = img.crop(crop_box)
                    if self.config.auto_contrast_clean:
                        cropped_img = ImageOps.autocontrast(cropped_img, cutoff=1)

                    out_name = f"panel_{panel_counter:03d}.{self.config.save_format.lower()}"
                    out_path = panels_dir / out_name
                    cropped_img.save(out_path, format=self.config.save_format, quality=95)
                    output_panel_paths.append(out_path)

                    manifest_data.append({
                        "panel_id": f"panel_{panel_counter:03d}",
                        "source_page": page_img_path.name,
                        "crop_bounds": list(crop_box),
                        "width": cropped_img.width,
                        "height": cropped_img.height,
                        "aspect_ratio": round(cropped_img.width / cropped_img.height, 4),
                        "type": panel.get("type", "standard"),
                        "notes": panel.get("notes", "")
                    })

                    panel_counter += 1

        # Save manifest for downstream audio/video synchronization
        write_json(manifest_path, {
            "chapter": str(chapter_num),
            "total_panels": len(output_panel_paths),
            "panels": manifest_data
        })

        console.print(f"[bold green]✓ Cropped {len(output_panel_paths)} panels successfully into:[/] {panels_dir}")
        if self.config.snap_to_gutters:
            console.print(
                f"[dim]  ↳ Gutter-snap refined {gutter_panels_adjusted}/{len(output_panel_paths)} panels "
                f"({gutter_edges_adjusted} edge(s) corrected from the LLM's guess via pixel analysis)[/]"
            )
        if self.config.dedupe_duplicate_panels and duplicate_panels_dropped:
            console.print(
                f"[dim]  ↳ Dedup removed {duplicate_panels_dropped} duplicate/overlapping panel crop(s) "
                f"before cropping (see warnings above) - crops.json may be worth reviewing.[/]"
            )

        # 1. Generate vision contact sheets if enabled or if requested
        if output_panel_paths and (self.config.create_sheets or asset_type == "sheets"):
            PanelSheetGenerator.create_panel_sheets(
                panel_paths=output_panel_paths,
                output_dir=sheets_dir,
                panels_per_sheet=self.config.panels_per_sheet
            )

        # 2. Package into sheets.zip or panels.zip
        if self.config.create_zip:
            create_vision_archive(self.config, chapter_dir, panels_dir, sheets_dir)

        return output_panel_paths
