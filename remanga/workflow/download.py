"""Downloading chapters from the manga's source (MangaDex, comix.to, ...), and showing what it lists."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.workflow.projects import settle_reading_direction


def print_chapter_list(listing: list[dict]) -> None:
    """The source's chapters with what this project has of each, compact enough
    for a long manga: one line per chapter, title when it has one."""
    marks = {"downloaded": "[green]✓ downloaded[/]", "partial": "[yellow]◐ partial[/]", "missing": "[dim]· new[/]"}
    console.print(f"\n[bold]The site lists {len(listing)} chapter(s)[/]")
    several = len({entry.get("source") for entry in listing}) > 1
    for entry in listing:
        title = f"  [dim]{_esc(entry['title'])}[/]" if entry.get("title") else ""
        if several:
            title = f"  [cyan]{_esc(entry.get('source', ''))}[/]{title}"
        pages = f"[dim]{entry['pages']}p[/]" if entry.get("pages") else ""
        console.print(f"  ch {entry['chapter']:>6}  {marks.get(entry['status'], entry['status']):<24} {pages}{title}")


def download(project: str, chapters: list[str], config: RemangaConfig, url: str | None = None,
             force: bool = False) -> list[Path]:
    """Each chapter from the source that has it (remanga.sources.plan_downloads),
    or every one from the manga at `url` when one is given."""
    from remanga.sources import client, plan_downloads, source_for

    plan = [(source_for(url), {"manga_url": url}, chapters)] if url else plan_downloads(project, chapters, config)
    paths: list[Path] = []
    for source, entry, todo in plan:
        if len(plan) > 1:
            console.print(f"[bold]{_esc(source.display_name)}:[/] chapter(s) {_esc(', '.join(todo))}")
        paths += client(source, config).download_chapters(project, todo, entry["manga_url"] or entry.get("manga_id"),
                                                          force=force)
    settle_reading_direction(project)
    return paths
