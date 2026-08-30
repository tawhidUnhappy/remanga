"""Builds the panels_zip package format - a zip archive purely for uploading
to an LLM chat interface, packaging individual panel crops. On by default
(see PackageConfig), since the lossless re-encode is a safe, no-downside
default upload format. Completely separate from panels/ itself, which is
untouched and stays the full-quality source video rendering reads from
(remanga.video.compose) - this module only ever READS those files, never
writes into that folder.

The actual packing (lossless re-encode, single-file-or-split-by-size,
per-part chapter_info.json) is remanga.cropper.zip_bundle.build_zip_bundle,
shared with remanga.cropper.llm_sheets - this module just points it at
panels_dir's images and the panels_zip/ folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from remanga.config import CropperConfig
from remanga.cropper.zip_bundle import build_zip_bundle


def build_llm_zip_bundle(
    config: CropperConfig,
    chapter_dir: Path,
    project_name: str,
    chapter_num: str,
    panel_paths: List[Path],
) -> List[Path]:
    """Builds panels_zip/panels_1.zip, panels_2.zip, ... - see module docstring."""
    package = config.package
    return build_zip_bundle(
        panel_paths, chapter_dir / "panels_zip", "panels",
        package.panels_zip, package.panels_zip_split, package.max_mb,
        project_name, chapter_num, "ZIP",
    )
