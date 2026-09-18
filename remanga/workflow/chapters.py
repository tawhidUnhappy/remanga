"""Which chapters a project has, which MangaDex lists, and where each one is
in the workflow."""

from __future__ import annotations

from remanga.chapters import chapter_sort_key, discover_chapters, expand_chapter_selection
from remanga.config import RemangaConfig
from remanga.json_io import has_real_json_content
from remanga.narration import page_files, panel_files
from remanga.paths import (
    get_audio_timing_path,
    get_crops_path,
    get_final_video_path,
    get_narration_path,
    get_pdf_dir,
)


def local_chapters(project: str) -> list[str]:
    return discover_chapters(project)


def mangadex_chapters(project: str, config: RemangaConfig, url: str | None = None,
                      refresh: bool = True) -> list[dict]:
    """Every chapter MangaDex lists for the project's manga right now, each
    with its local status (downloaded / partial / missing). Fetched fresh by
    default, so a chapter published since the last run is in it."""
    from remanga.downloader import MangaDexDownloader

    return MangaDexDownloader(config.downloader).list_chapters_with_status(project, url, force_refresh=refresh)


def select_chapters(raw: str, available: list[str]) -> list[str]:
    """'1', '1-5', '1-5,8', or 'all', against the chapters available."""
    text = (raw or "").strip()
    if not text or text.lower() == "all":
        return sorted(available, key=chapter_sort_key)
    return expand_chapter_selection(text, available)


def chapter_state(project: str, chapter: str) -> str:
    """Where a chapter is, in words: the next thing it needs."""
    if not page_files(project, chapter):
        return "not downloaded"
    if get_final_video_path(project, chapter, create=False).exists():
        return "video done"
    if has_real_json_content(get_narration_path(project, chapter)):
        return "narration pasted - make the video"
    if any(get_pdf_dir(project, chapter, create=False).glob("panels_*.pdf")):
        return "PDF ready - waiting for the narration"
    if panel_files(project, chapter):
        return "panels cut - make the PDF"
    if has_marks(project, chapter):
        return "panels marked - make the PDF"
    return "downloaded - mark the panels"


def has_audio(project: str, chapter: str) -> bool:
    """Whether this chapter has been narrated before - what makes remaking the
    video a thing to offer at all."""
    return get_audio_timing_path(project, chapter, create=False).exists()


def has_marks(project: str, chapter: str) -> bool:
    """Whether this chapter's panels have been marked (crops.json saved)."""
    return has_real_json_content(get_crops_path(project, chapter))


def has_panels(project: str, chapter: str) -> bool:
    return bool(panel_files(project, chapter))
