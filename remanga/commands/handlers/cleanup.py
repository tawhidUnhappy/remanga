"""Handlers for the destructive commands: restart (fixed presets), wipe
(keep any combination), and wipe-chapters (the same, across many chapters).

All three used to repeat the same shape - list what would go, print it,
confirm, delete, report - with three slightly different wordings and three
chances to get the "kept:" line wrong. That shape is `_confirm_and_delete`
below now, so what's listed is always exactly what's deleted, and every one
of them reports the same way."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List

from remanga import reset
from remanga.commands.selection import parse_chapter_selection, resolve_wipe_keep
from remanga.config import RemangaConfig
from remanga.console import console, display_path
from remanga.tui import confirm
from remanga.webui import launch_and_wait as launch_panel_marker


def _preview(per_chapter: Dict[str, List[Path]]) -> int:
    """Prints exactly what's about to be deleted, chapter by chapter, and
    returns the total count. One chapter prints as a flat list; several
    print grouped, since "42 items" across nine chapters is not something
    anyone can check without seeing which chapter each belongs to."""
    total = sum(len(items) for items in per_chapter.values())
    multi = len(per_chapter) > 1
    scope = f" across {len(per_chapter)} chapter(s)" if multi else ""
    console.print(f"[bold red]The following will be permanently deleted{scope}:[/]")
    for chapter, items in per_chapter.items():
        if multi:
            console.print(f"[bold]Chapter {chapter}:[/]")
        for item in items:
            console.print(f"  [dim]- {display_path(item)}[/]")
    return total


def _confirm_and_delete(
    *,
    per_chapter: Dict[str, List[Path]],
    kept: str,
    force: bool,
    delete: Callable[[str], None],
    nothing_message: str,
    done_message: str,
) -> bool:
    """The shared confirm-then-delete flow. Returns whether anything was
    actually deleted."""
    per_chapter = {chapter: items for chapter, items in per_chapter.items() if items}
    if not per_chapter:
        console.print(f"[dim]{nothing_message}[/]")
        return False

    total = _preview(per_chapter)
    console.print(f"[dim]Kept: {kept}.[/]")

    if not force and not confirm(
        f"Permanently delete these {total} item(s)?",
        default=False, note="this cannot be undone",
    ):
        console.print("[dim]Cancelled - nothing was deleted.[/]")
        return False

    for chapter in per_chapter:
        delete(chapter)
    # "{chapters}" is filled in after filtering, so a multi-chapter wipe
    # reports the chapters it actually touched rather than every chapter that
    # was selected - several of which may have had nothing left to delete.
    console.print(f"[bold green]✓ {done_message.replace('{chapters}', ', '.join(per_chapter))}[/]")
    return True


def restart(params: Dict[str, Any], config: RemangaConfig) -> None:
    project, chapter = params["project"], params["chapter"]
    mode = reset.RESTART_MODE_BY_NAME[params.get("mode") or "hard"]
    candidates = reset.restart_candidates(project, chapter, mode=mode.deletes_like)

    deleted = _confirm_and_delete(
        per_chapter={chapter: candidates},
        kept=mode.keeps,
        force=bool(params.get("force")),
        delete=lambda ch: reset.restart_chapter(
            project, ch, mode=mode.deletes_like,
            reverify_downloads=not params.get("no_reverify"),
        ),
        nothing_message=(
            f"Nothing to delete for a {mode.label.lower()} - everything it would keep "
            f"is already all that's here."
        ),
        done_message=f"Chapter {chapter} {mode.label.lower()} complete. Downloaded pages kept — ready to reprocess.",
    )

    if deleted and mode.reopen_marker:
        console.print("[yellow]Reopening the Panel Marker - your existing marks are pre-loaded (MAGI won't touch them).[/]")
        launch_panel_marker(project, chapter, config.marker)
        console.print(f"[bold green]✓ Marks for Chapter {chapter} updated and saved.[/]")


def wipe(params: Dict[str, Any], config: RemangaConfig) -> None:
    project, chapter = params["project"], params["chapter"]
    keep_names = resolve_wipe_keep(params.get("keep"))
    candidates = [e for e in reset.wipeable_entries(project, chapter) if e.name not in keep_names]

    _confirm_and_delete(
        per_chapter={chapter: candidates},
        kept=", ".join(sorted(keep_names)) or "(nothing - full wipe)",
        force=bool(params.get("force")),
        # Downloads are always re-verified afterward, regardless of whether
        # pages/ itself was kept - a wipe that deleted it should end up
        # re-downloaded rather than just missing.
        delete=lambda ch: reset.wipe_chapter(project, ch, keep_names, reverify_downloads=True),
        nothing_message="Nothing to wipe - everything here is already in the keep list.",
        done_message=f"Chapter {chapter} wipe complete. Downloaded pages re-verified.",
    )


def wipe_chapters(params: Dict[str, Any], config: RemangaConfig) -> None:
    project = params["project"]
    keep_names = resolve_wipe_keep(params.get("keep"))
    chapters = parse_chapter_selection(params["chapters"], project)
    if not chapters:
        console.print(f"[dim]No chapters matched '{params['chapters']}' for project '{project}'.[/]")
        return

    per_chapter = {
        chapter: [e for e in reset.wipeable_entries(project, chapter) if e.name not in keep_names]
        for chapter in chapters
    }

    _confirm_and_delete(
        per_chapter=per_chapter,
        kept=", ".join(sorted(keep_names)) or "(nothing - full wipe)",
        force=bool(params.get("force")),
        delete=lambda ch: reset.wipe_chapter(project, ch, keep_names, reverify_downloads=True),
        nothing_message="Nothing to wipe across the selected chapter(s) - everything is already in the keep list.",
        done_message="Wipe complete for chapter(s) {chapters}. Downloaded pages re-verified.",
    )
