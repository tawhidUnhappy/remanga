"""Post-crop bookkeeping for a chapter: writing panels_manifest.json, printing
the summary line, and packaging the vision-upload asset (sheets/zip). Split
out of crop.py so CoordinateCropper's loop isn't tangled up with reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.archive import create_vision_archive
from remanga.cropper.sheets import PanelSheetGenerator
from remanga.json_io import write_json
from remanga.paths import load_project_metadata


def write_manifest(manifest_path: Path, chapter_num: str, panel_paths: List[Path], manifest_entries: List[Dict[str, Any]]) -> None:
    write_json(manifest_path, {
        "chapter": str(chapter_num),
        "total_panels": len(panel_paths),
        "panels": manifest_entries,
    })


def write_chapter_info(chapter_info_path: Path, project_name: str, chapter_num: str) -> None:
    """Writes chapter_info.json - bundled into the vision zip alongside the panel
    images (see archive.py) so the LLM narrating this chapter always has authoritative
    project/manga/chapter identity straight from the upload, instead of depending on
    whatever the human happens to type in the chat (see prompts/narration.md's
    "Chapter Identity" section, which reads this file for exactly that)."""
    meta = load_project_metadata(project_name)
    write_json(chapter_info_path, {
        "project_name": project_name,
        "manga_name": meta.get("manga_title", ""),
        "manga_url": meta.get("manga_url", ""),
        "chapter": str(chapter_num),
    })


def print_crop_summary(
    panels_dir: Path,
    total_panels: int,
    config: CropperConfig,
    gutter_panels_adjusted: int,
    gutter_edges_adjusted: int,
    panels_trimmed: int,
    duplicate_panels_dropped: int,
) -> None:
    console.print(f"[bold green]✓ Cropped {total_panels} panels successfully into:[/] {panels_dir}")
    if config.snap_to_gutters:
        console.print(
            f"[dim]  ↳ Gutter-snap refined {gutter_panels_adjusted}/{total_panels} panels "
            f"({gutter_edges_adjusted} edge(s) corrected from the marked box via pixel analysis)[/]"
        )
    if config.trim_panel_whitespace and panels_trimmed:
        console.print(
            f"[dim]  ↳ Trimmed leftover blank margin off {panels_trimmed}/{total_panels} panels[/]"
        )
    if config.dedupe_duplicate_panels and duplicate_panels_dropped:
        console.print(
            f"[dim]  ↳ Dedup removed {duplicate_panels_dropped} duplicate/overlapping panel crop(s) "
            f"before cropping (see warnings above) - crops.json may be worth reviewing.[/]"
        )


def package_outputs(config: CropperConfig, chapter_dir: Path, panels_dir: Path, sheets_dir: Path, panel_paths: List[Path]) -> None:
    asset_type = getattr(config, "vision_asset_type", "sheets").lower()

    # 1. Generate vision contact sheets if enabled or if requested
    if panel_paths and (config.create_sheets or asset_type == "sheets"):
        PanelSheetGenerator.create_panel_sheets(
            panel_paths=panel_paths,
            output_dir=sheets_dir,
            panels_per_sheet=config.panels_per_sheet,
        )

    # 2. Package into sheets.zip or panels.zip
    if config.create_zip:
        create_vision_archive(config, chapter_dir, panels_dir, sheets_dir)
