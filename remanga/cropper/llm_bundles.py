"""Coordinates every size-capped LLM upload bundle format behind one call, so
crop.py/crop_report.py don't need to know about each format individually -
currently the zip (remanga.cropper.llm_zip), the PDF (remanga.cropper.
llm_pdf), and the contact-sheets zip (remanga.cropper.llm_sheets), each
independently activated (PackageConfig.panels_zip_active/pdf_active/
sheets_zip_active) but sharing one size cap (PackageConfig.max_mb). Adding
a fourth format later only means wiring it in here."""

from __future__ import annotations

from pathlib import Path
from typing import List

from remanga.config import CropperConfig
from remanga.cropper.llm_pdf import build_llm_pdf_bundle
from remanga.cropper.llm_sheets import build_llm_sheets_bundle
from remanga.cropper.llm_zip import build_llm_zip_bundle


def build_llm_bundles(
    config: CropperConfig,
    chapter_dir: Path,
    project_name: str,
    chapter_num: str,
    panel_paths: List[Path],
    sheet_paths: List[Path],
) -> None:
    build_llm_zip_bundle(config, chapter_dir, project_name, chapter_num, panel_paths)
    build_llm_pdf_bundle(config, chapter_dir, project_name, chapter_num, panel_paths)
    build_llm_sheets_bundle(config, chapter_dir, project_name, chapter_num, sheet_paths)


def is_up_to_date(config: CropperConfig, chapter_dir: Path) -> bool:
    """True if every *active* bundle format already has at least one part on
    disk (an inactive format never blocks this). Used by crop.py's resume-check
    to decide whether a chapter that's already fully cropped still needs its
    LLM bundle(s) topped up, without forcing a full re-crop just for that."""
    panels_pdf_dir = chapter_dir / "panels_pdf"
    zip_ok = not config.package.panels_zip_active or any((chapter_dir / "panels_zip").glob("panels_*.zip"))
    pdf_ok = not config.package.pdf_active or any(panels_pdf_dir.glob("panels_*.pdf")) or any(panels_pdf_dir.glob("panels_*.zip"))
    sheets_ok = not config.package.sheets_zip_active or any((chapter_dir / "sheets_zip").glob("sheets_*.zip"))
    return zip_ok and pdf_ok and sheets_ok
