"""Cheap health checks the wizard runs on its own, without being asked."""

from __future__ import annotations

from remanga.console import console


def warn_panel_narration_mismatches(project: str) -> None:
    """Runs the moment a project is selected - cheap enough (no ffprobe,
    just directory listings and JSON reads) to do on every selection rather
    than only on an explicit `verify`.

    Catches the footgun that costs the most to notice late: narration.json's
    panel_id must equal the stem of a file in panels/, so a mismatch means a
    re-crop happened after narration was written (or vice versa), silently
    leaving panels unnarrated. Purely informational - it never blocks
    entering the menu."""
    from remanga.verify import project_panel_narration_mismatches

    mismatches = project_panel_narration_mismatches(project)
    if not mismatches:
        return
    console.print(f"\n[bold yellow]⚠ Panel/narration mismatch in {len(mismatches)} chapter(s):[/]")
    for chapter_num, issue in mismatches:
        console.print(f"  [yellow]Chapter {chapter_num}:[/] {issue}")
    console.print(
        "[dim]  -> likely a re-crop after narration was written, or vice versa - re-run "
        "crop/write/review for the affected chapter(s) to line them back up.[/]"
    )
