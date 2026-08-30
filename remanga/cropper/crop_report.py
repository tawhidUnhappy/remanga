"""Post-crop bookkeeping for a chapter: writing panels_manifest.json, printing
the summary line, and packaging the vision-upload asset (sheets/zip). Split
out of crop.py so CoordinateCropper's loop isn't tangled up with reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.llm_bundles import build_llm_bundles
from remanga.cropper.sheets import PanelSheetGenerator
from remanga.json_io import write_json
from remanga.paths import chapter_identity_fields


def write_manifest(manifest_path: Path, chapter_num: str, panel_paths: List[Path], manifest_entries: List[Dict[str, Any]]) -> None:
    write_json(manifest_path, {
        "chapter": str(chapter_num),
        "total_panels": len(panel_paths),
        "panels": manifest_entries,
    })


def write_chapter_info(chapter_info_path: Path, project_name: str, chapter_num: str) -> None:
    """Writes chapter_info.json - bundled into every LLM upload zip/PDF part
    alongside the images (see llm_bundles.py) so the LLM narrating this
    chapter always has authoritative project/manga/chapter identity straight
    from the upload, instead of depending on whatever the human happens to
    type in the chat (see prompts/narration.md's "Chapter Identity" section,
    which reads this file for exactly that)."""
    write_json(chapter_info_path, chapter_identity_fields(project_name, chapter_num))


def ensure_sheets_generated(config: CropperConfig, project_name: str, chapter_num, panel_paths: List[Path], sheets_dir: Path) -> List[Path]:
    """Generates contact sheet composites into `sheets_dir` if anything
    actually needs them right now: `package.sheets` is on, or the
    sheets_zip package format (`PackageConfig.sheets_zip_active`) is -
    either one is enough, since checking sheets_zip alone should just work
    without also having to separately turn generation on. Shared by
    package_outputs (every fresh crop) and crop.py's resume-check top-up
    path (an already-cropped chapter that just had the sheets bundle turned
    on, so sheets/ doesn't exist yet). Returns whatever's on disk in
    `sheets_dir` either way, so a caller that doesn't need to regenerate
    anything can still use what's already there."""
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


def package_outputs(
    config: CropperConfig,
    chapter_dir: Path,
    sheets_dir: Path,
    panel_paths: List[Path],
    project_name: str,
    chapter_num: str,
) -> None:
    # 1. Generate vision contact sheets if anything needs them right now.
    sheet_paths = ensure_sheets_generated(config, project_name, chapter_num, panel_paths, sheets_dir)

    # 2. Package whichever size-capped zip/PDF format(s) are active
    # (panels_zip/, panels_pdf/, and/or sheets_zip/) - see
    # remanga.cropper.llm_bundles/PackageConfig. This is the only zip
    # mechanism a chapter has - no separate "primary archive" exists to
    # also account for.
    build_llm_bundles(config, chapter_dir, project_name, chapter_num, panel_paths, sheet_paths)

