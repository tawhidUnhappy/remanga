"""The whole workflow, one function per step:

    download   chapters from MangaDex into chapters/chapter_N/pages/
    make_pdf   the pages as PDF parts (pdf/chapter_N/), and what to do with them
    make_video the pasted narration checked, narrated with Kokoro, mixed with
               background music, and rendered over the pages

The command line (cli.py) and the menus (wizard.py) both call these, so the
two can't do a step differently."""

from __future__ import annotations

from pathlib import Path

from remanga.chapters import chapter_sort_key, discover_chapters, expand_chapter_selection
from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc
from remanga.json_io import has_real_json_content
from remanga.narration import PROMPT_PATH, load_narration, page_files, story_so_far
from remanga.paths import (
    chapter_identity_fields,
    get_final_video_path,
    get_narration_path,
    get_pdf_dir,
    load_project_metadata,
    save_project_metadata,
)
from remanga.pdf import build_pages_pdf
from remanga.pdf.manifest_info import MEMORY_KEY

# MangaDex's originalLanguage -> how that market's comics are read.
READING_DIRECTION_BY_LANGUAGE = {
    "ja": "right_to_left",
    "ko": "left_to_right",
    "zh": "left_to_right",
    "zh-hk": "left_to_right",
    "en": "left_to_right",
}


# --- chapters ---------------------------------------------------------------


def local_chapters(project: str) -> list[str]:
    return discover_chapters(project)


def mangadex_chapters(project: str, config: RemangaConfig, url: str | None = None,
                      refresh: bool = False) -> list[dict]:
    """Every chapter MangaDex lists for the project's manga, each with its
    local status (downloaded / partial / missing)."""
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
    if any(get_pdf_dir(project, chapter, create=False).glob("pages_*.pdf")):
        return "PDF ready - waiting for the narration"
    return "downloaded - make the PDF"


# --- download ---------------------------------------------------------------


def download(project: str, chapters: list[str], config: RemangaConfig, url: str | None = None,
             force: bool = False) -> list[Path]:
    from remanga.downloader import MangaDexDownloader

    paths = MangaDexDownloader(config.downloader).download_chapters(project, chapters, url, force=force)
    settle_reading_direction(project)
    return paths


def settle_reading_direction(project: str) -> str:
    """The manga's reading direction, recorded from MangaDex's original
    language when it isn't yet - right to left when that says nothing."""
    meta = load_project_metadata(project)
    if meta.get("reading_direction"):
        return meta["reading_direction"]
    language = str(meta.get("original_language") or "").lower()
    direction = READING_DIRECTION_BY_LANGUAGE.get(language, "right_to_left")
    save_project_metadata(project, {"reading_direction": direction})
    console.print(f"[dim]Reading direction: {direction.replace('_', '-')}"
                  + (f" (MangaDex original language '{language}')" if language in READING_DIRECTION_BY_LANGUAGE
                     else " (the manga default)") + "[/]")
    return direction


# --- PDF --------------------------------------------------------------------


def make_pdf(project: str, chapter: str, config: RemangaConfig) -> list[Path]:
    """The chapter's pages as PDF parts, with the chapter's identity and the
    story so far on each part's first page, then what to upload and where the
    reply goes. An empty narration.json is put in place to paste into."""
    pages = page_files(project, chapter)
    if not pages:
        raise FileNotFoundError(f"Chapter {chapter} has no downloaded pages - download it first.")
    settle_reading_direction(project)

    info = dict(chapter_identity_fields(project, chapter))
    memory = story_so_far(project)
    last = str((memory or {}).get("last_chapter_processed", ""))
    # Only memory written before this chapter: re-making an earlier chapter's
    # PDF must not hand the LLM what happens later.
    if memory and (not last or chapter_sort_key(last) < chapter_sort_key(str(chapter))):
        info[MEMORY_KEY] = memory
    parts = build_pages_pdf(pages, get_pdf_dir(project, chapter), config.pdf.max_mb, info)

    narration = get_narration_path(project, chapter)
    if not narration.exists():
        narration.write_text("", encoding="utf-8")
    print_handoff(project, chapter, parts)
    return parts


def print_handoff(project: str, chapter: str, parts: list[Path]) -> None:
    console.print(f"\n[bold]Chapter {chapter}: give these to the LLM[/]")
    console.print(f"  {display_path(PROMPT_PATH, wrap=False)}  [dim](the instructions)[/]")
    for part in parts:
        console.print(f"  {display_path(part, wrap=False)}")
    console.print("[bold]Paste its reply into[/]")
    console.print(f"  {display_path(get_narration_path(project, chapter), wrap=False)}")
    console.print("[dim]Then make the video.[/]")


# --- video ------------------------------------------------------------------


def make_video(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> Path:
    """Checks the pasted narration, narrates each story page with Kokoro,
    mixes in the background music, and renders the pages. Every stage reuses
    what is already done and still current."""
    from remanga.audio import TTSEngine, mix_master_audio
    from remanga.video import VideoRenderer

    pages, check = load_narration(project, chapter)
    console.print(f"[bold]Chapter {chapter}:[/] narration checked - {len(pages)} page(s) to narrate")
    if check.warnings:
        console.print(f"[yellow]{len(check.warnings)} thing(s) worth a look in the narration:[/]")
        for warning in check.warnings:
            console.print(f"  [yellow]- {_esc(warning)}[/]")

    TTSEngine(config.tts, config.audio).generate_narration_audio(project, chapter, pages, force=force)
    mix_master_audio(project, chapter, config.audio, force=force)
    return VideoRenderer(config.system, config.video).render_video(project, chapter, force=force)
