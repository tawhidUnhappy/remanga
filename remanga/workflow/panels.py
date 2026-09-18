"""The two steps that turn pages into panels: marking them in the Panel Marker
web UI, and cutting them out of the pages."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.cropper import CoordinateCropper
from remanga.narration import page_files, panel_files
from remanga.paths import get_crops_path
from remanga.workflow.chapters import has_marks


def mark(project: str, chapters: list[str], config: RemangaConfig) -> list[str]:
    """Opens the Panel Marker in a browser tab and waits there: MAGI v3 finds
    the panels when asked, they are fixed by hand, and saving writes each
    chapter's crops.json. Returns the chapters saved."""
    from remanga.webui import launch_and_wait_all

    marked = [c for c in chapters if page_files(project, c)]
    if not marked:
        raise FileNotFoundError("None of the chosen chapters have pages yet - download them first.")
    saved = launch_and_wait_all(project, marked, config.marker)
    console.print(f"[bold green]✓ Marks saved for {len(saved)} chapter(s)[/]")
    return saved


def cut_panels(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> list[Path]:
    """The marked panels, cut out of the pages into chapters/chapter_N/panels/.
    Already-cut panels are reused unless the marks changed since (or `force`)."""
    if not has_marks(project, chapter):
        raise FileNotFoundError(f"Chapter {chapter} has no marked panels yet - mark them in the Panel Marker "
                                f"first.")
    newest_panel = max((p.stat().st_mtime for p in panel_files(project, chapter)), default=0.0)
    stale = get_crops_path(project, chapter).stat().st_mtime > newest_panel
    return CoordinateCropper(config.cropper).crop_chapter_from_json(project, chapter, force=force or stale)
