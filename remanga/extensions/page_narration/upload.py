"""Building a chapter's pages upload: the downloaded pages, untouched, as the
PDF formats of PageNarrationConfig - through the same size-capped builder the
panel and grid PDFs use (remanga.cropper.llm_pdf: JPEG pages embedded as their
own bytes, everything else lossless unless the cap needs otherwise)."""

from __future__ import annotations

from pathlib import Path

from remanga.cropper.llm_pdf import build_pdf_bundle
from remanga.extensions.page_narration.config import PageNarrationConfig
from remanga.extensions.page_narration.paths import chapter_page_files, get_page_upload_dir, get_reply_path
from remanga.paths import get_chapter_dir, load_project_metadata

# Written into every part's info, so the prompt can tell a pages upload from
# a panels one.
UPLOAD_INFO = {"mode": "pages"}


def ensure_reply_file(project_name: str, chapter_num: str) -> Path:
    """page_narration.json, created empty (0 bytes - "not written yet"),
    unless something is already there, which is never touched."""
    path = get_reply_path(project_name, chapter_num)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return path


def build_page_upload(settings: PageNarrationConfig, project_name: str, chapter_num: str) -> list[Path]:
    pages = chapter_page_files(project_name, chapter_num)
    if not pages:
        raise FileNotFoundError(
            f"No downloaded pages for chapter {chapter_num}: {get_chapter_dir(project_name, chapter_num) / 'pages'}"
            f"\nRun `download` first."
        )
    if not settings.any_active:
        raise ValueError("Every pages format is switched off - turn one on in Settings → Page narration.")
    if "reading_direction" not in load_project_metadata(project_name):
        raise ValueError(
            f"Missing 'reading_direction' for project '{project_name}' - the LLM needs it to read each "
            f"page's panels in order. Run `remanga interactive` once for this project, or add "
            f"\"reading_direction\": \"right_to_left\" (or \"left_to_right\") to projects/{project_name}/project.json."
        )
    written = build_pdf_bundle(
        pages, get_page_upload_dir(project_name, chapter_num, create=False), "pages",
        settings.pages_pdf, settings.pages_pdf_splite, settings.pages_pdf_zip, settings.pages_pdf_zip_splite,
        settings.max_mb, project_name, chapter_num, "PAGES PDF", extra_info=UPLOAD_INFO,
    )
    if not written:
        raise RuntimeError(f"Chapter {chapter_num}'s pages upload could not be built - see the message above.")
    ensure_reply_file(project_name, chapter_num)
    return written


def upload_files(project_name: str, chapter_num: str) -> list[Path]:
    upload_dir = get_page_upload_dir(project_name, chapter_num, create=False)
    if not upload_dir.exists():
        return []
    return sorted([*upload_dir.glob("pages_*.pdf"), *upload_dir.glob("pages_*.zip")])
