"""Post-crop bookkeeping for a chapter: recording panel info into this
project's shared manifest.json, printing the summary line, and packaging
the vision-upload asset (sheets/zip). Split out of crop.py so
CoordinateCropper's loop isn't tangled up with reporting."""

from __future__ import annotations

from pathlib import Path
from typing import List

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.cropper.llm_bundles import build_llm_bundles
from remanga.cropper.sheet_folders import PanelFolderGenerator
from remanga.cropper.sheets import PanelSheetGenerator
from remanga.paths import get_sheets_dir, get_sheets_folders_dir, update_manifest_chapter


def write_manifest(project_name: str, chapter_num: str, panel_paths: List[Path]) -> None:
    """Records that this chapter has been cropped into {manga}/manifest.json's
    "panels" section (see paths.update_manifest_chapter) - just the count,
    used as crop.py's own resume marker ("has this chapter been cropped
    before"). Deliberately NOT a per-panel dump (path/crop_bounds/width/
    height/... for every single panel, as the old standalone
    panels_manifest.json this replaces used to carry) - `manifest_entries`
    already lives in full, per-panel, wherever it's actually needed
    (panels/ itself, and each package format's own per-part manifest - see
    remanga.cropper.manifest_info); repeating all of it a second time here
    just to sit unread was the exact bloat this file replaced three
    per-chapter dead files to get away from."""
    update_manifest_chapter(project_name, chapter_num, "panels", {
        "total_panels": len(panel_paths),
    })


def ensure_sheets_generated(config: CropperConfig, project_name: str, chapter_num, panel_paths: List[Path]) -> List[Path]:
    """Generates contact sheet composites into {manga}/sheets/chapter_N/ if
    anything actually needs them right now: `package.sheets` is on, or the
    sheets_zip package format (`PackageConfig.sheets_zip_active`) is -
    either one is enough, since checking sheets_zip alone should just work
    without also having to separately turn generation on. Shared by
    package_outputs (every fresh crop) and crop.py's resume-check top-up
    path (an already-cropped chapter that just had the sheets bundle turned
    on, so sheets/chapter_N/ doesn't exist yet). Returns whatever's on disk
    either way, so a caller that doesn't need to regenerate anything can
    still use what's already there."""
    sheets_dir = get_sheets_dir(project_name, chapter_num, create=False)
    needs_sheets = config.package.sheets or config.package.sheets_zip_active
    if panel_paths and needs_sheets:
        return PanelSheetGenerator.create_panel_sheets(
            project_name=project_name,
            chapter_num=chapter_num,
            panel_paths=panel_paths,
            output_dir=sheets_dir,
            panels_per_sheet=config.panels_per_sheet,
        )
    return sorted(p for p in sheets_dir.iterdir() if p.is_file()) if sheets_dir.exists() else []


def ensure_panel_folders_generated(config: CropperConfig, project_name: str, chapter_num, panel_paths: List[Path]) -> List[Path]:
    """Generates the `sheets_folders` package format into
    {manga}/sheets_folders/chapter_N/ if `package.sheets_folders` is on -
    the plain-folder alternative to `ensure_sheets_generated` above (see
    remanga/cropper/sheet_folders.py). Mirrors that function's "return
    what's already there otherwise" shape."""
    folders_dir = get_sheets_folders_dir(project_name, chapter_num, create=False)
    if panel_paths and config.package.sheets_folders:
        return PanelFolderGenerator.create_panel_folders(
            panel_paths=panel_paths,
            output_dir=folders_dir,
            panels_per_folder=config.panels_per_folder,
        )
    return sorted(p for p in folders_dir.iterdir() if p.is_dir()) if folders_dir.exists() else []


def print_crop_summary(
    panels_dir: Path,
    total_panels: int,
    config: CropperConfig,
    gutter_panels_adjusted: int,
    gutter_edges_adjusted: int,
    panels_trimmed: int,
    duplicate_panels_dropped: int,
) -> None:
    console.print(f"[bold green]✓ Cropped {total_panels} panels successfully into:[/] {_esc(str(panels_dir))}")
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


def package_outputs(
    config: CropperConfig,
    panel_paths: List[Path],
    project_name: str,
    chapter_num: str,
) -> None:
    # 1. Generate vision contact sheets if anything needs them right now.
    sheet_paths = ensure_sheets_generated(config, project_name, chapter_num, panel_paths)

    # 1b. Generate the plain-folder alternative (`sheets_folders`) if it's on.
    ensure_panel_folders_generated(config, project_name, chapter_num, panel_paths)

    # 2. Package whichever size-capped zip/PDF format(s) are active
    # (panels_zip/, panels_pdf/, and/or sheets_zip/) - see
    # remanga.cropper.llm_bundles/PackageConfig. This is the only zip
    # mechanism a chapter has - no separate "primary archive" exists to
    # also account for.
    build_llm_bundles(config, project_name, chapter_num, panel_paths, sheet_paths)
