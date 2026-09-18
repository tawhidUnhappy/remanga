"""Downloading chapters from MangaDex, and showing what it lists."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.workflow.projects import settle_reading_direction


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
