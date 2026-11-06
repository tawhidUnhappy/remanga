"""Seasons - chapters taken a block at a time, the way an anime rolls out 12
episodes and then the next 12 (downloader.season_chapters, 12 by default).
The first season starts where the brief says (chapter 1 unless the story
starts later); each next season is the next block of the chapters the site
lists after the last one this project has."""

from __future__ import annotations

from remanga.chapters import chapter_sort_key
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc


def next_season(available: list[str], have: list[str], size: int, start: str | None = None) -> list[str]:
    """The next `size` chapters of `available`, in reading order: those after
    the last one in `have`; with none had, from `start` (else the first)."""
    ordered = sorted(dict.fromkeys(available), key=chapter_sort_key)
    if have:
        last = max(chapter_sort_key(c) for c in have)
        ordered = [c for c in ordered if chapter_sort_key(c) > last]
    elif start:
        first = chapter_sort_key(start)
        ordered = [c for c in ordered if chapter_sort_key(c) >= first]
    return ordered[:size]


def season_label(chapters: list[str]) -> str:
    return chapters[0] if len(chapters) == 1 else f"{chapters[0]}-{chapters[-1]}"


def listing_next_season(rows: list[dict], size: int) -> list[str]:
    """The next season, from a chapter list's rows (chapter + status): what is
    on disk (downloaded, partial or local only) counts as had."""
    have = [r["chapter"] for r in rows if r["status"] in ("downloaded", "partial", "local")]
    # A listing can hold the same number twice (two sources); available needs it once.
    available = [r["chapter"] for r in rows if r["status"] != "local"]
    return next_season(available, have, size)


def add_season(project: str, config: RemangaConfig) -> list[str]:
    """Downloads the project's next season and returns its chapters ([] when
    the site has nothing after the last chapter you have)."""
    from remanga import workflow

    size = config.downloader.season_chapters
    chapters = listing_next_season(workflow.mangadex_chapters(project, config), size)
    if not chapters:
        console.print("[green]Nothing after the last chapter you have - the manga has no more chapters listed.[/]")
        return []
    console.print(f"[bold cyan]Next season:[/] chapters {_esc(season_label(chapters))} ({len(chapters)})")
    workflow.download(project, chapters, config)
    return chapters
