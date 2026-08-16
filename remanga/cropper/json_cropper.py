from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageOps
from rich.console import Console

from remanga.config import CropperConfig, get_chapter_dir

console = Console()


class CoordinateCropper:
    def __init__(self, config: Optional[CropperConfig] = None):
        self.config = config or CropperConfig()

    def crop_chapter_from_json(self, project_name: str, chapter_num: str) -> List[Path]:
        """
        Reads `crops.json` in the chapter directory, crops all specified panels from
        the downloaded pages, and writes output sequentially to the `panels/` folder.
        """
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        crops_json_path = chapter_dir / "crops.json"
        pages_dir = chapter_dir / "pages"
        panels_dir = chapter_dir / "panels"

        if not crops_json_path.exists():
            raise FileNotFoundError(
                f"Missing crop instructions file: {crops_json_path}\n"
                f"Please create this file from LLM prompt output before running the cropper."
            )

        if not pages_dir.exists() or not list(pages_dir.glob("page_*.*")):
            raise FileNotFoundError(
                f"Pages directory is empty: {pages_dir}\n"
                f"Please download the chapter pages first."
            )

        panels_dir.mkdir(parents=True, exist_ok=True)

        with open(crops_json_path, "r", encoding="utf-8") as f:
            crop_data = json.load(f)

        pages_list = crop_data.get("pages", [])
        if not pages_list:
            raise ValueError(f"Invalid crops.json: No 'pages' array found in {crops_json_path}")

        console.print(f"[cyan]Processing panel cropping for chapter {chapter_num}...[/]")
        
        panel_counter = 1
        output_panel_paths: List[Path] = []
        manifest_data = []

        for page_entry in pages_list:
            page_filename = page_entry.get("page_filename")
            page_index = page_entry.get("page_index")
            
            # Locate corresponding page file
            page_img_path = self._locate_page_file(pages_dir, page_filename, page_index)
            if not page_img_path or not page_img_path.exists():
                console.print(f"[yellow]Warning: Could not locate page image for entry: {page_entry}. Skipping...[/]")
                continue

            with Image.open(page_img_path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
                img_w, img_h = img.size

                panels = page_entry.get("panels", [])
                for panel in panels:
                    box = panel.get("box_1000") or panel.get("box_pixel") or panel.get("coordinates")
                    if not box or len(box) != 4:
                        console.print(f"[yellow]Skipping invalid panel box: {panel}[/]")
                        continue

                    # Parse coordinates [ymin, xmin, ymax, xmax]
                    crop_box = self._calculate_pixel_bounds(box, img_w, img_h, is_1000="box_1000" in panel or max(box) <= 1000)
                    
                    # Apply margin padding
                    crop_box = self._apply_padding(crop_box, img_w, img_h, self.config.margin_padding_pixels)

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
                        "notes": panel.get("notes", "")
                    })

                    panel_counter += 1

        # Save panels manifest for audio/video sync step
        manifest_path = chapter_dir / "panels_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({"chapter": str(chapter_num), "total_panels": len(output_panel_paths), "panels": manifest_data}, f, indent=2)

        console.print(f"[bold green]✓ Cropped {len(output_panel_paths)} panels successfully into:[/] {panels_dir}")
        return output_panel_paths

    def _locate_page_file(self, pages_dir: Path, filename: Optional[str], page_index: Optional[int]) -> Optional[Path]:
        """Resolves target page image path using filename or index fallback."""
        if filename and (pages_dir / filename).exists():
            return pages_dir / filename

        if page_index is not None:
            # Match page_001.png, page_01.jpg, etc.
            candidates = list(pages_dir.glob(f"page_{page_index:03d}.*")) or list(pages_dir.glob(f"page_{page_index:02d}.*")) or list(pages_dir.glob(f"page_{page_index}.*"))
            if candidates:
                return candidates[0]

        # Sorted alphabetical fallback
        all_pages = sorted(list(pages_dir.glob("page_*.*")))
        if page_index and 1 <= page_index <= len(all_pages):
            return all_pages[page_index - 1]

        return None

    def _calculate_pixel_bounds(self, box: List[int], img_w: int, img_h: int, is_1000: bool) -> Tuple[int, int, int, int]:
        """Converts [ymin, xmin, ymax, xmax] into Pillow crop box (left, upper, right, lower)."""
        ymin, xmin, ymax, xmax = box

        if is_1000:
            left = int((xmin / 1000.0) * img_w)
            top = int((ymin / 1000.0) * img_h)
            right = int((xmax / 1000.0) * img_w)
            bottom = int((ymax / 1000.0) * img_h)
        else:
            left = int(xmin)
            top = int(ymin)
            right = int(xmax)
            bottom = int(ymax)

        # Enforce valid bounding constraints
        left = max(0, min(left, img_w - 1))
        top = max(0, min(top, img_h - 1))
        right = max(left + 1, min(right, img_w))
        bottom = max(top + 1, min(bottom, img_h))

        return (left, top, right, bottom)

    def _apply_padding(self, bounds: Tuple[int, int, int, int], img_w: int, img_h: int, padding: int) -> Tuple[int, int, int, int]:
        """Expands bounds slightly by padding pixels while preserving image bounds."""
        left, top, right, bottom = bounds
        return (
            max(0, left - padding),
            max(0, top - padding),
            min(img_w, right + padding),
            min(img_h, bottom + padding)
        )