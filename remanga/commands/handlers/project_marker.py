"""Project-wide Panel Marker handlers: marking every chapter in one tab, and
looking through every chapter's marks without being able to change them."""

from __future__ import annotations

from typing import Any

from remanga.commands.handlers.common import chosen_chapters
from remanga.config import RemangaConfig
from remanga.console import console


def mark_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """Marks panels for every chapter in the project, in ONE browser tab.

    The per-chapter `mark` command opens the marker, waits for one save, and
    exits - so marking a whole manga was that ceremony twenty times over: a
    new server, a new tab, a new MAGI load, and the terminal to come back to
    in between. This hands the marker the whole list instead. Saving a
    chapter writes its crops.json and swaps the next chapter's pages into the
    page that's already open (see webui/marker_session.py), and the chapter
    arrows go back to one already done - so checking chapter 3's marks after
    doing chapter 9 costs a click, not another run.

    Chapters with nothing downloaded are dropped by the session itself, with
    a line naming them: a chapter that can't be marked shouldn't become a
    blank screen in the middle of a long pass."""
    from remanga.webui import launch_and_wait_all

    project = params["project"]
    chapters = chosen_chapters(params, "download some first")
    if not chapters:
        return

    saved = launch_and_wait_all(project, chapters, config.marker)
    console.print(
        f"[bold green]✓ Marking session finished[/] [dim]- crops.json written for "
        f"{len(saved)} chapter(s).[/]"
    )


def view_marks(params: dict[str, Any], config: RemangaConfig) -> None:
    """The same whole-project marker session, with every edit taken away.

    `mark-all` is for doing the work; this is for the pass afterwards, when
    what you want is to look at all of it and be sure - every chapter, every
    page, every panel, navigable from the sidebar outline, with no way to
    nudge a box by accident while checking it. Read-only is enforced by the
    server (see MarkerSession.read_only), not just hidden in the browser: the
    point of opening it is to trust that looking changed nothing.

    Nothing is written, including on the way out - no crops.json is saved
    when a chapter is left or when the session ends. MAGI never runs either;
    detection fills in marks nobody saved, which is exactly the kind of thing
    a verification pass must not invent."""
    from remanga.webui import launch_and_wait_all

    project = params["project"]
    chapters = chosen_chapters(params, "nothing to look at")
    if not chapters:
        return

    launch_and_wait_all(project, chapters, config.marker, read_only=True)
    console.print("[bold green]✓ Viewer closed[/] [dim]- nothing was changed.[/]")
