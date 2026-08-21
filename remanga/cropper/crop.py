from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageOps
from rich.console import Console

from remanga.config import CropperConfig
from remanga.cropper.geometry import apply_padding, calculate_pixel_bounds
from remanga.cropper.sheets import PanelSheetGenerator
from remanga.json_io import read_json, write_json
from remanga.paths import get_chapter_dir

console = Console()


class CoordinateCropper:
    def __init__(self, config: Optional[CropperConfig] = None):
        self.config = config or CropperConfig()

    def _create_vision_archive(self, chapter_dir: Path, panels_dir: Path, sheets_dir: Optional[Path]) -> Path:
        """
        Packages cropped assets into either sheets.zip (2x2 contact sheets) or panels.zip (individual crops)
        based on the user's configured vision_asset_type.
        """
        asset_type = getattr(self.config, "vision_asset_type", "sheets").lower()
        zip_filename = "panels.zip" if asset_type == "panels" else "sheets.zip"
        zip_path = chapter_dir / zip_filename

        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if asset_type == "sheets":
                if sheets_dir and sheets_dir.exists() and list(sheets_dir.glob("sheet_*.*")):
                    for s in sorted(list(sheets_dir.glob("sheet_*.*"))):
                        zf.write(s, arcname=s.name)
                else:
                    for p in sorted(list(panels_dir.glob("panel_*.*"))):
                        zf.write(p, arcname=p.name)
            else:
                for p in sorted(list(panels_dir.glob("panel_*.*"))):
                    zf.write(p, arcname=p.name)

            manifest = chapter_dir / "panels_manifest.json"
            if manifest.exists():
                zf.write(manifest, arcname="panels_manifest.json")

        console.print(f"[bold green]✓ Created Vision Archive ({zip_filename} - Mode: {asset_type.upper()}):[/] {zip_path}")
        return zip_path

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

        for page_entry in pages_list:
            is_story_page = page_entry.get("is_story_page", True)
            panels = page_entry.get("panels", [])

            if not is_story_page or not panels:
                page_desc = page_entry.get("page_filename") or f"page index {page_entry.get('page_index')}"
                note_str = page_entry.get("notes", "non-story/duplicate")
                console.print(f"[dim yellow]Skipping non-story page ({page_desc}): {note_str}[/]")
                continue

            page_filename = page_entry.get("page_filename")
            page_index = page_entry.get("page_index")

            page_img_path = self._locate_page_file(pages_dir, page_filename, page_index)
            if not page_img_path or not page_img_path.exists():
                console.print(f"[yellow]Warning: Could not locate page image for: {page_entry}. Skipping...[/]")
                continue

            with Image.open(page_img_path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
                img_w, img_h = img.size

                for panel in panels:
                    box = panel.get("box_1000") or panel.get("box_pixel") or panel.get("coordinates")
                    if not box or len(box) != 4:
                        console.print(f"[yellow]Skipping invalid panel coordinate entry: {panel}[/]")
                        continue

                    is_normalized = "box_1000" in panel or max(box) <= 1000
                    crop_box = calculate_pixel_bounds(box, img_w, img_h, is_1000=is_normalized)

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

        # 1. Generate vision contact sheets if enabled or if requested
        if output_panel_paths and (self.config.create_sheets or asset_type == "sheets"):
            PanelSheetGenerator.create_panel_sheets(
                panel_paths=output_panel_paths,
                output_dir=sheets_dir,
                panels_per_sheet=self.config.panels_per_sheet
            )

        # 2. Package into sheets.zip or panels.zip
        if self.config.create_zip:
            self._create_vision_archive(chapter_dir, panels_dir, sheets_dir)

        return output_panel_paths

    def _locate_page_file(self, pages_dir: Path, filename: Optional[str], page_index: Optional[int]) -> Optional[Path]:
        """Resolves target page image path using filename or numeric index fallback."""
        if filename and (pages_dir / filename).exists():
            return pages_dir / filename

        if page_index is not None:
            candidates = (
                list(pages_dir.glob(f"page_{page_index:03d}.*")) +
                list(pages_dir.glob(f"page_{page_index:02d}.*")) +
                list(pages_dir.glob(f"page_{page_index}.*"))
            )
            if candidates:
                return candidates[0]

        all_pages = sorted(list(pages_dir.glob("page_*.*")))
        if page_index and 1 <= page_index <= len(all_pages):
            return all_pages[page_index - 1]

        return None