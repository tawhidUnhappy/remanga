"""Packages cropped panel/sheet assets into the chapter's primary vision-upload
zip archive (sheets.zip/panels.zip) - the "legacy" single-archive method
prompts/narration.md documents alongside the size-capped LLM bundles
(remanga.cropper.llm_zip/llm_pdf). Every image written in gets the same
lossless shrink those bundles use (remanga.cropper.image_codec) - one
implementation of "smaller without losing anything" for every zip this
project builds, not a separate copy here."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import List, Optional

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.image_codec import smallest_lossless_encoding


def _write_images(zf: zipfile.ZipFile, image_paths: List[Path]) -> None:
    for path in image_paths:
        data, ext = smallest_lossless_encoding(path)
        zf.writestr(path.stem + ext, data)


def create_vision_archive(
    config: CropperConfig, chapter_dir: Path, panels_dir: Path, sheets_dir: Optional[Path]
) -> Path:
    """Packages cropped assets into either sheets.zip (2x2 contact sheets) or
    panels.zip (individual crops) based on the user's configured
    primary_archive_format."""
    asset_type = getattr(config, "primary_archive_format", "panels").lower()
    zip_filename = config.expected_zip_name
    zip_path = chapter_dir / zip_filename

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        if asset_type == "sheets" and sheets_dir and sheets_dir.exists() and list(sheets_dir.glob("sheet_*.*")):
            _write_images(zf, sorted(sheets_dir.glob("sheet_*.*")))
        else:
            _write_images(zf, sorted(panels_dir.glob("panel_*.*")))

        manifest = chapter_dir / "panels_manifest.json"
        if manifest.exists():
            zf.write(manifest, arcname="panels_manifest.json")

        # Project/manga/chapter identity for the LLM narrating this chapter -
        # see cropper/crop_report.py:write_chapter_info and
        # prompts/narration.md's "Chapter Identity" section.
        chapter_info = chapter_dir / "chapter_info.json"
        if chapter_info.exists():
            zf.write(chapter_info, arcname="chapter_info.json")

    console.print(f"[bold green]✓ Created Vision Archive ({zip_filename} - Mode: {asset_type.upper()}):[/] {zip_path}")
    return zip_path
