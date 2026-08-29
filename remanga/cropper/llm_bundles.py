"""Coordinates every size-capped LLM upload bundle format behind one call, so
crop.py/crop_report.py don't need to know about each format individually -
currently the zip (remanga.cropper.llm_zip) and the PDF
(remanga.cropper.llm_pdf), both independently toggled
(LLMBundleConfig.zip_enabled/pdf_enabled) but sharing one size cap
(LLMBundleConfig.max_mb). Adding a third format later only means
wiring it in here."""

from __future__ import annotations

from pathlib import Path
from typing import List

from remanga.config import CropperConfig
from remanga.cropper.llm_pdf import build_llm_pdf_bundle
from remanga.cropper.llm_zip import build_llm_zip_bundle


def build_llm_bundles(
    config: CropperConfig,
    chapter_dir: Path,
    project_name: str,
    chapter_num: str,
    panel_paths: List[Path],
) -> None:
    build_llm_zip_bundle(config, chapter_dir, project_name, chapter_num, panel_paths)
    build_llm_pdf_bundle(config, chapter_dir, project_name, chapter_num, panel_paths)


def is_up_to_date(config: CropperConfig, chapter_dir: Path) -> bool:
    """True if every *enabled* bundle format already has at least one part on
    disk (a disabled format never blocks this). Used by crop.py's resume-check
    to decide whether a chapter that's already fully cropped still needs its
    LLM bundle(s) topped up, without forcing a full re-crop just for that."""
    zip_ok = not config.llm_bundle.zip_enabled or any((chapter_dir / "panels_zip").glob("panels_*.zip"))
    pdf_ok = not config.llm_bundle.pdf_enabled or any((chapter_dir / "panels_pdf").glob("panels_*.pdf"))
    return zip_ok and pdf_ok
