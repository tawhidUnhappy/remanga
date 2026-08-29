"""Chapter-level crop orchestration: reads crops.json, resolves and crops every
panel, then packages the vision upload archive. The actual box math lives in
remanga.cropper.panel_boxes/gutter/seams/dedupe, one page's worth of cropping
lives in remanga.cropper.crop_page, and manifest/summary/packaging lives in
remanga.cropper.crop_report - this module just wires the pipeline stages
together in order."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.crop_page import crop_page
from remanga.cropper.crop_report import ensure_sheets_generated, package_outputs, print_crop_summary, write_chapter_info, write_manifest
from remanga.cropper.llm_bundles import build_llm_bundles, is_up_to_date
from remanga.json_io import has_real_json_content, read_json
from remanga.paths import get_chapter_dir


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
        chapter_info_path = chapter_dir / "chapter_info.json"
        expected_zip = chapter_dir / self.config.expected_zip_name

        if not has_real_json_content(crops_json_path):
            raise FileNotFoundError(
                f"Missing or empty crop instructions file: {crops_json_path}\n"
                f"Please mark this chapter's panels in the Panel Marker web UI first."
            )

        if not pages_dir.exists() or not list(pages_dir.glob("page_*.*")):
            raise FileNotFoundError(
                f"Pages directory is empty: {pages_dir}\n"
                f"Please download the chapter pages first."
            )

        # RESUME CHECK: If panels already exist and force=False, verify and skip
        # the (expensive) re-crop. Still tops up any enabled LLM bundle
        # format that's missing (a lightweight re-encode of already-cropped
        # panels, not a full re-crop) - so a chapter cropped before that
        # format existed, or with it previously disabled, gets it built once
        # on its next run instead of never.
        #
        # The primary archive only has to exist if config.create_zip is
        # actually on - otherwise it never gets built at all (see
        # crop_report.py's package_outputs), and requiring it here would mean
        # a chapter with create_zip off could never take this fast path,
        # forcing a full re-crop on every single run for no reason.
        existing_panels = sorted(panels_dir.glob("panel_*.*"))
        primary_archive_ready = not self.config.create_zip or expected_zip.exists()
        if not force and existing_panels and manifest_path.exists() and primary_archive_ready:
            status = expected_zip.name if self.config.create_zip else "no primary archive (create_zip is off)"
            console.print(f"[bold green]✓ Found {len(existing_panels)} panels already cropped and {status} ready! Skipping re-crop.[/]")
            if not is_up_to_date(self.config, chapter_dir):
                sheet_paths = ensure_sheets_generated(self.config, existing_panels, sheets_dir)
                build_llm_bundles(self.config, chapter_dir, project_name, chapter_num, existing_panels, sheet_paths)
            return existing_panels

        # Clear existing panels directory before fresh cropping
        panels_dir.mkdir(parents=True, exist_ok=True)
        for old_file in panels_dir.glob("panel_*.*"):
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
        manifest_data = []
        gutter_panels_adjusted = 0
        gutter_edges_adjusted = 0
        duplicate_panels_dropped = 0
        panels_trimmed = 0

        for page_entry in pages_list:
            result = crop_page(page_entry, pages_dir, panels_dir, panel_counter, self.config)
            if result is None:
                continue

            panel_counter = result.next_panel_counter
            output_panel_paths.extend(result.panel_paths)
            manifest_data.extend(result.manifest_entries)
            gutter_panels_adjusted += result.gutter_panels_adjusted
            gutter_edges_adjusted += result.gutter_edges_adjusted
            duplicate_panels_dropped += result.duplicate_panels_dropped
            panels_trimmed += result.panels_trimmed

        write_manifest(manifest_path, chapter_num, output_panel_paths, manifest_data)
        write_chapter_info(chapter_info_path, project_name, chapter_num)
        print_crop_summary(
            panels_dir, len(output_panel_paths), self.config,
            gutter_panels_adjusted, gutter_edges_adjusted, panels_trimmed, duplicate_panels_dropped,
        )
        package_outputs(self.config, chapter_dir, panels_dir, sheets_dir, output_panel_paths, project_name, chapter_num)

        return output_panel_paths
