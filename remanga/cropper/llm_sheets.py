"""Builds the sheets_zip package format - the same idea as
remanga.cropper.llm_zip, just packaging 2x2 contact sheet composites
(sheet_001.___, sheet_002.___, ... - whichever lossless extension each one
won, see remanga.cropper.sheets) instead of individual panel crops. Off by
default (see PackageConfig) - most users pick either individual panels
(llm_zip.py) or sheets, not both, and panels is the default. This bundle can
be built (and the sheet_* composites it needs generated) whether or not
`GenerateConfig.sheets` is separately on - see crop_report.py's
ensure_sheets_generated, which generates sheets/ whenever this format is
active, checking `generate.sheets` too.

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
    package = config.package
    return build_zip_bundle(
        sheet_paths, chapter_dir / "sheets_zip", "sheets",
        package.sheets_zip, package.sheets_zip_split, package.max_mb,
        project_name, chapter_num, "SHEETS ZIP",
    )
