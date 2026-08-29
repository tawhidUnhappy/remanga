"""Builds the sheets-zip variant of the LLM upload bundle - the same idea as
remanga.cropper.llm_zip, just packaging 2x2 contact sheet composites
(sheet_001.png, sheet_002.png, ... - the same content sheets.zip/the primary
archive would, when vision_asset_type is "sheets") instead of individual
panel crops. Off by default (see LLMBundleConfig) - most users pick either
individual panels (llm_zip.py) or sheets, not both, and panels is the
default. Completely independent of `vision_asset_type`: this bundle can be
built (and the sheet_*.png composites it needs generated) even while the
primary archive is packaging panels.zip - see crop_report.py's
package_outputs, which generates sheets/ whenever this format is active,
not only when vision_asset_type is "sheets".

Per-part chapter_info.json entries reuse the same `panel_id_start`/
`panel_id_end` field names remanga.cropper.llm_zip uses - here they hold
sheet stems (e.g. "sheet_003") rather than panel stems, since a part is
still just "the first/last item packed into it" regardless of which kind of
image that is; not worth a separate schema for what's otherwise identical
bookkeeping.

The actual packing (lossless re-encode, single-file-or-split-by-size,
per-part chapter_info.json) is remanga.cropper.zip_bundle.build_zip_bundle,
shared with llm_zip.py - this module just points it at sheets_dir's images
and the sheets_zip/ folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from remanga.config import CropperConfig
from remanga.cropper.zip_bundle import build_zip_bundle


def build_llm_sheets_bundle(
    config: CropperConfig,
    chapter_dir: Path,
    project_name: str,
    chapter_num: str,
    sheet_paths: List[Path],
) -> List[Path]:
    """Builds sheets_zip/sheets_1.zip, sheets_2.zip, ... - see module docstring."""
    bundle = config.llm_bundle
    return build_zip_bundle(
        sheet_paths, chapter_dir / "sheets_zip", "sheets",
        bundle.sheets_enabled, bundle.sheets_split_enabled, bundle.max_mb,
        project_name, chapter_num, "SHEETS ZIP",
    )
