"""Chapter-level crop orchestration: reads crops.json, resolves and crops every
panel, then packages whichever LLM upload formats are active. The actual box
math lives in remanga.cropper.panel_boxes/gutter/seams/dedupe, one page's
worth of cropping lives in remanga.cropper.crop_page, and
manifest/summary/packaging lives in remanga.cropper.crop_report - this module
just wires the pipeline stages together in order."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.crop_page import crop_page
from remanga.cropper.crop_report import ensure_panel_folders_generated, ensure_sheets_generated, package_outputs, print_crop_summary, write_manifest
from remanga.cropper.llm_bundles import build_llm_bundles, is_up_to_date
from remanga.json_io import has_real_json_content, read_json
from remanga.paths import get_chapter_dir, load_project_metadata, read_manifest


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

        if not has_real_json_content(crops_json_path):
            raise FileNotFoundError(
                f"Missing or empty crop instructions file: {crops_json_path}\n"
                f"Please mark this chapter's panels in the Panel Marker web UI first."
            )

        if not pages_dir.exists() or not any(p.is_file() for p in pages_dir.iterdir()):
            raise FileNotFoundError(
                f"Pages directory is empty: {pages_dir}\n"
                f"Please download the chapter pages first."
            )

        # reading_direction feeds every panels_pdf/panels_zip/sheets_zip
        # chapter_info.json via chapter_identity_fields (see
        # remanga.paths.metadata) - required before packaging runs below, not
        # just cosmetic. `remanga interactive` asks for it once per project
        # and saves it to project.json; this direct/scripted `crop` entry
        # point has no prompt UI of its own, so it fails clearly instead of
        # silently defaulting or shipping a bundle with a guessed direction.
        # This is the pattern to follow for any future required-but-missing
        # project.json/config.json field: interactive callers prompt and
        # save it up front, non-interactive callers fail fast here with
        # exactly what's missing and how to fix it.
        if "reading_direction" not in load_project_metadata(project_name):
            raise ValueError(
                f"Missing 'reading_direction' for project '{project_name}' - required before "
                f"panels_pdf/panels_zip/sheets_zip can be packaged. Set it by running "
                f"`remanga interactive` once for this project (it will ask and save it), or add "
                f"\"reading_direction\": \"right_to_left\" (or \"left_to_right\") directly to "
                f"projects/{project_name}/project.json."
            )

        # RESUME CHECK: If panels already exist and force=False, verify and skip
        # the (expensive) re-crop. Still tops up any enabled package format
        # that's missing (a lightweight re-encode of already-cropped panels,
        # not a full re-crop) - so a chapter cropped before that format
        # existed, or with it previously disabled, gets it built once on its
        # next run instead of never. "Already cropped" is decided by this
        # chapter having a "panels" entry in the shared manifest.json (see
        # crop_report.write_manifest) - the crop step's own record that it
        # ran to completion for this chapter, same role the old standalone
        # panels_manifest.json's mere existence used to play.
        existing_panels = sorted(p for p in panels_dir.iterdir() if p.is_file()) if panels_dir.exists() else []
        already_cropped = bool(read_manifest(project_name).get("chapters", {}).get(str(chapter_num), {}).get("panels"))
        if not force and existing_panels and already_cropped:
            console.print(f"[bold green]✓ Found {len(existing_panels)} panels already cropped! Skipping re-crop.[/]")
            if not is_up_to_date(self.config, project_name, chapter_num):
                sheet_paths = ensure_sheets_generated(self.config, project_name, chapter_num, existing_panels)
                build_llm_bundles(self.config, project_name, chapter_num, existing_panels, sheet_paths)
            ensure_panel_folders_generated(self.config, project_name, chapter_num, existing_panels)
            return existing_panels

        # Clear existing panels directory before fresh cropping - a full wipe,
        # not a pattern-matched one, so anything that doesn't belong there
        # (stray files, a leftover from an old naming scheme) never survives
        # into the fresh crop.
        panels_dir.mkdir(parents=True, exist_ok=True)
        for old_file in panels_dir.iterdir():
            if old_file.is_file():
                try:
                    old_file.unlink()
                except Exception:
                    pass

        crop_data = read_json(crops_json_path)
        pages_list = crop_data.get("pages", [])
        if not pages_list:
            raise ValueError(f"Invalid crops.json: No 'pages' array found in {crops_json_path}")

        console.print(f"[cyan]Processing panel cropping for chapter {chapter_num}...[/]")

        output_panel_paths: List[Path] = []
        gutter_panels_adjusted = 0
        gutter_edges_adjusted = 0
        duplicate_panels_dropped = 0
        panels_trimmed = 0

        for page_number, page_entry in enumerate(pages_list, start=1):
            result = crop_page(page_entry, pages_dir, panels_dir, chapter_num, page_number, self.config)
            if result is None:
                continue

            output_panel_paths.extend(result.panel_paths)
            gutter_panels_adjusted += result.gutter_panels_adjusted
            gutter_edges_adjusted += result.gutter_edges_adjusted
            duplicate_panels_dropped += result.duplicate_panels_dropped
            panels_trimmed += result.panels_trimmed

        write_manifest(project_name, chapter_num, output_panel_paths)
        print_crop_summary(
            panels_dir, len(output_panel_paths), self.config,
            gutter_panels_adjusted, gutter_edges_adjusted, panels_trimmed, duplicate_panels_dropped,
        )
        package_outputs(self.config, output_panel_paths, project_name, chapter_num)

        return output_panel_paths
