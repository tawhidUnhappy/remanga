"""Builds the zip variant of the LLM upload bundle - a second vision archive
purely for uploading to an LLM chat interface, packaging individual panel
crops (the same content panels.zip/the primary archive would, when
vision_asset_type is "panels"). On by default (see LLMBundleConfig), since
the lossless re-encode is a safe, no-downside win over the primary archive
for this purpose. Completely separate from:
- panels/ itself, which is untouched and stays the full-quality source video
  rendering reads from (remanga.video.compose) - this module only ever READS
  those files, never writes into that folder.
- the primary vision archive (remanga.cropper.archive's sheets.zip/panels.zip),
  which keeps working exactly as it did before this module existed - the
  "previous legacy method" prompts/narration.md still documents alongside this
  one (and alongside remanga.cropper.llm_pdf/llm_sheets, the other formats).

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
    bundle = config.llm_bundle
    return build_zip_bundle(
        panel_paths, chapter_dir / "panels_zip", "panels",
        bundle.zip_enabled, bundle.zip_split_enabled, bundle.max_mb,
        project_name, chapter_num, "ZIP",
    )
