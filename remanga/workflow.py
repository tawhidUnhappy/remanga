"""The whole workflow, one function per step:

    download   chapters from MangaDex into chapters/chapter_N/pages/
    make_pdf   the pages as PDF parts (pdf/chapter_N/), and what to do with them
    make_video the pasted narration checked, narrated with Kokoro, mixed with
               background music, and rendered over the pages

The command line (cli.py) and the menus (wizard.py) both call these, so the
two can't do a step differently."""

from __future__ import annotations

import re
from pathlib import Path

from remanga.chapters import chapter_sort_key, discover_chapters, expand_chapter_selection
from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc
from remanga.json_io import has_real_json_content
from remanga.narration import PROMPT_PATH, load_narration, page_files, story_so_far
from remanga.paths import (
    GENERATED_KINDS,
    chapter_identity_fields,
    get_chapter_dir,
    get_final_video_path,
    get_generated_dir,
    get_narration_path,
    get_pdf_dir,
    get_project_dir,
    list_projects,
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


# --- projects ---------------------------------------------------------------

# Longest folder name made from a title; cut at a word.
PROJECT_NAME_MAX = 40


def project_name_from_title(title: str) -> str:
    """A folder name from a manga's title, in the projects' PascalCase style:
    "I Died Protecting My Comrades..." -> "IDiedProtectingMyComrades...",
    cut at a whole word."""
    words = re.findall(r"[A-Za-z0-9]+", title)
    name = ""
    for word in words:
        piece = word[:1].upper() + word[1:]
        if name and len(name) + len(piece) > PROJECT_NAME_MAX:
            break
        name += piece
    return name or "Manga"


def create_project(source: str, config: RemangaConfig) -> str:
    """A project for the manga at `source` (a MangaDex URL, ID or a title to
    search), named after its English title, with its title, original language
    and reading direction fetched. A manga that already has a project opens
    that project instead. Returns the project's name."""
    from remanga.downloader import MangaDexDownloader

    resolver = MangaDexDownloader(config.downloader).resolver
    manga_id = resolver.parse_manga_id(source)
    for project in list_projects():
        if project["manga_id"] == manga_id:
            console.print(f"[green]You already have this manga:[/] {_esc(project['name'])}")
            return project["name"]

    info = resolver.get_manga_info(manga_id)
    base = project_name_from_title(info["english_title"] or info["title"])
    taken = {project["name"].casefold() for project in list_projects()}
    name, n = base, 2
    while name.casefold() in taken:
        name, n = f"{base}{n}", n + 1
    direction = READING_DIRECTION_BY_LANGUAGE.get(info["original_language"], "right_to_left")
    save_project_metadata(name, {
        "project_name": name,
        "manga_url": source.strip(),
        "manga_id": manga_id,
        "manga_title": info["title"],
        "original_language": info["original_language"],
        "reading_direction": direction,
    })
    console.print(f"[bold green]✓ New project:[/] {_esc(name)}\n"
                  f"  {_esc(info['english_title'] or info['title'])}\n"
                  f"  [dim]reads {direction.replace('_', '-')}"
                  + (f" (original language '{info['original_language']}')" if info["original_language"] else "")
                  + "[/]")
    return name


# --- chapters ---------------------------------------------------------------


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
    if any(get_pdf_dir(project, chapter, create=False).glob("pages_*.pdf")):
        return "PDF ready - waiting for the narration"
    return "downloaded - make the PDF"


# --- download ---------------------------------------------------------------


def print_chapter_list(listing: list[dict]) -> None:
    """MangaDex's chapters with what this project has of each, compact enough
    for a long manga: one line per chapter, title when it has one."""
    marks = {"downloaded": "[green]✓ downloaded[/]", "partial": "[yellow]◐ partial[/]", "missing": "[dim]· new[/]"}
    console.print(f"\n[bold]MangaDex lists {len(listing)} chapter(s)[/] [dim](fetched just now)[/]")
    for entry in listing:
        title = f"  [dim]{_esc(entry['title'])}[/]" if entry.get("title") else ""
        pages = f"[dim]{entry['pages']}p[/]" if entry.get("pages") else ""
        console.print(f"  ch {entry['chapter']:>6}  {marks.get(entry['status'], entry['status']):<24} {pages}{title}")


def download(project: str, chapters: list[str], config: RemangaConfig, url: str | None = None,
             force: bool = False) -> list[Path]:
    from remanga.downloader import MangaDexDownloader

    paths = MangaDexDownloader(config.downloader).download_chapters(project, chapters, url, force=force)
    settle_reading_direction(project)
    return paths


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return path.resolve() != root.resolve()
    except ValueError:
        return False


def _chapter_paths(project: str, chapter: str, *, with_pages: bool) -> list[Path]:
    """What resetting (or, `with_pages`, deleting) a chapter removes - each
    one checked to be a chapter folder or file strictly inside this project,
    so a blank or odd project/chapter name can never widen it."""
    if not str(project).strip() or not str(chapter).strip():
        raise ValueError("A project and a chapter are needed.")
    project_dir = get_project_dir(project)
    chapter_dir = get_chapter_dir(project, chapter)
    paths = [get_generated_dir(project, kind, chapter, create=False) for kind in GENERATED_KINDS]
    paths.append(chapter_dir if with_pages else get_narration_path(project, chapter))
    for path in paths:
        if not _inside(path, project_dir) or not path.name.startswith(("chapter_", "narration.json")):
            raise ValueError(f"Refusing to delete {path} - it isn't one chapter's file inside {project_dir}.")
    return [path for path in paths if path.exists()]


def reset_chapter(project: str, chapter: str, *, delete_pages: bool = False) -> list[Path]:
    """Deletes a chapter's PDF, pasted narration, audio and video - and, with
    `delete_pages`, its downloaded pages too, removing the chapter. Returns
    what was removed."""
    import shutil

    removed = _chapter_paths(project, chapter, with_pages=delete_pages)
    for path in removed:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return removed


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
