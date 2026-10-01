"""The two steps that turn pages into panels: marking them (in whatever the
chapter's layout plug-in opens - remanga.layouts), and cutting them out."""

from __future__ import annotations

from pathlib import Path

from remanga import plugins
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.cropper import CoordinateCropper
from remanga.layouts import layout_for
from remanga.narration import page_files, panel_files
from remanga.paths import get_crops_path
from remanga.workflow.chapters import has_marks


def mark(project: str, chapters: list[str], config: RemangaConfig) -> list[str]:
    """Opens each chapter's marker in a browser tab and waits there - the Panel
    Marker for pages (MAGI v3 finds the panels when asked), the Strip Marker
    for a long strip - grouped by layout, in layout order. Saving writes each
    chapter's crops.json. Returns the chapters saved."""
    marked = [c for c in chapters if page_files(project, c)]
    if not marked:
        raise FileNotFoundError("None of the chosen chapters have pages yet - download them first.")
    by_layout: dict[str, list[str]] = {}
    for chapter in marked:
        by_layout.setdefault(layout_for(project, chapter).name, []).append(chapter)
    saved: list[str] = []
    for layout in plugins.items("layout"):
        if by_layout.get(layout.name):
            saved += plugins.call(layout.mark, project, by_layout[layout.name], config)
    console.print(f"[bold green]✓ Marks saved for {len(saved)} chapter(s)[/]")
    return saved


def cut_panels(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> list[Path]:
    """The marked panels, cut out of the pages into chapters/chapter_N/panels/.
    Already-cut panels are reused unless the marks changed since (or `force`)."""
    layout = layout_for(project, chapter)
    if layout.prepare_cut:
        plugins.call(layout.prepare_cut, project, chapter)   # e.g. a strip's crops.json follows its marks
    if not has_marks(project, chapter):
        raise FileNotFoundError(f"Chapter {chapter} has no marked panels yet - mark them in the Panel Marker "
                                f"first.")
    newest_panel = max((p.stat().st_mtime for p in panel_files(project, chapter)), default=0.0)
    stale = get_crops_path(project, chapter).stat().st_mtime > newest_panel
    return CoordinateCropper(config.cropper).crop_chapter_from_json(project, chapter, force=force or stale)
