"""What a finished crop records and says: the chapter's panel count in the
project manifest (crop.py's own "this chapter is cropped" marker) and the
summary line."""

from __future__ import annotations

from pathlib import Path

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.paths import update_manifest_chapter


def write_manifest(project_name: str, chapter_num: str, panel_paths: list[Path]) -> None:
    update_manifest_chapter(project_name, chapter_num, "panels", {"total_panels": len(panel_paths)})


def print_crop_summary(panels_dir: Path, panel_count: int, config: CropperConfig,
                       gutter_panels_adjusted: int, gutter_edges_adjusted: int, panels_trimmed: int,
                       duplicate_panels_dropped: int, panels_painted: int) -> None:
    console.print(f"[bold green]✓ {panel_count} panel(s) cut[/] [dim]{_esc(str(panels_dir))}[/]")
    notes = []
    if config.snap_to_gutters and gutter_panels_adjusted:
        notes.append(f"{gutter_panels_adjusted} panel(s) snapped to gutters ({gutter_edges_adjusted} edge(s))")
    if panels_trimmed:
        notes.append(f"{panels_trimmed} trimmed of blank margin")
    if duplicate_panels_dropped:
        notes.append(f"{duplicate_panels_dropped} duplicate(s) dropped")
    if panels_painted:
        notes.append(f"{panels_painted} painted clear of a neighbour")
    if notes:
        console.print(f"[dim]  {', '.join(notes)}[/]")
