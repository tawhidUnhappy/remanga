"""Handlers for the project-wide commands: whole-manga compilation, remix,
status, integrity verification, and the two whole-project setup passes -
fetching every chapter, and giving every chapter a narration file to fill
in."""

from __future__ import annotations

from typing import Any

from remanga.commands.selection import split_chapters
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.full_recap import FullRecapCompiler, discover_chapters
from remanga.remix import remix_project
from remanga.reset import DEFAULT_REBUILD_MODE, REBUILD_MODE_BY_NAME
from remanga.status import render_status_panel
from remanga.verify import verify_project


def full_recap(params: dict[str, Any], config: RemangaConfig) -> None:
    # One ordered choice in, three booleans out. The modes are strictly
    # increasing in destructiveness (see reset.REBUILD_MODES), so they cannot
    # be combined into a contradiction the way the three separate flags they
    # replaced could - "force but also regenerate-all", "effects and all at
    # once" - each of which someone had to resolve in their head before
    # answering.
    mode = REBUILD_MODE_BY_NAME.get(
        str(params.get("rebuild") or DEFAULT_REBUILD_MODE), REBUILD_MODE_BY_NAME[DEFAULT_REBUILD_MODE],
    )
    FullRecapCompiler(config).compile_full_manga(
        params["project"], force=mode.force,
        chapters=split_chapters(params.get("chapters")),
        regenerate_all=mode.wipe == "project",
        regenerate_effects=mode.wipe == "derived",
        regenerate_sources=mode.wipe == "sources",
    )


def remix(params: dict[str, Any], config: RemangaConfig) -> None:
    remix_project(
        params["project"], config, chapters=split_chapters(params.get("chapters")),
        bgm_override=params.get("bgm"), rejoin=not params.get("no_rejoin"),
    )


def status(params: dict[str, Any], config: RemangaConfig) -> None:
    console.print(render_status_panel(params["project"], params["chapter"]))


def verify(params: dict[str, Any], config: RemangaConfig) -> None:
    verify_project(
        params["project"], chapters=split_chapters(params.get("chapters")),
        check_video=not params.get("no_video"),
    )


def download_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """Every chapter MangaDex lists for this project's manga, downloaded.

    `download-chapters` already downloads several - but it is a *picker*:
    it exists to choose which ones, and choosing is exactly what "I want
    the whole manga" isn't. This asks nothing about which chapters, because
    the answer is all of them.

    What "all of them" means is the feed for this project's manga in the
    configured translation language (`downloader.language`, English by
    default), reduced to the newest upload of each chapter number - see
    MangaDexResolver.latest_versions for why a chapter can be in there more
    than once. Every chapter goes through download_chapter's own
    verify-and-fill-in-what's-missing path, so re-running this on a project
    that already has most of the manga costs a check per chapter and
    downloads only what's actually absent."""
    from remanga.downloader import MangaDexDownloader
    from remanga.tui import confirm, is_interactive

    project = params["project"]
    downloader = MangaDexDownloader(config.downloader)
    entries = downloader.list_chapters_with_status(
        project, params.get("url"), force_refresh=bool(params.get("refetch")),
    )
    if not entries:
        console.print(
            f"[yellow]MangaDex lists no chapters in '{config.downloader.language}' for this "
            f"manga - nothing to download.[/]"
        )
        return

    numbers = [entry["chapter"] for entry in entries]
    have = sum(1 for entry in entries if entry["status"] == "downloaded")
    console.print(
        f"[bold]{len(numbers)} chapter(s)[/] on MangaDex in "
        f"[bold]{config.downloader.language}[/] [dim](latest upload of each)[/] · "
        f"[green]{have} already downloaded[/] · [yellow]{len(numbers) - have} to fetch[/]"
    )
    # Only a real terminal is asked. A scripted `remanga download-all -p x`
    # already said what it wanted on the command line, and blocking it on a
    # confirmation nobody can answer would be the whole point of the flag,
    # undone.
    if is_interactive() and not confirm(
        f"Download all {len(numbers)} chapter(s) now?", default=True,
        note="already-downloaded chapters are verified, not re-fetched"
             + (" · --force re-fetches every one of them clean" if not params.get("force") else ""),
    ):
        return
    downloader.download_chapters(project, numbers, params.get("url"), force=bool(params.get("force")))


def narration_init_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """A blank narration.json for every chapter in the project - zero bytes,
    not "{}", not "[]".

    The whole-project form of the `init-narration` pipeline step, for the
    obvious reason: a project is set up once and then worked chapter by
    chapter, and "give every chapter its empty script file" is part of
    setting it up, not something to re-answer twenty times.

    Chapters that already hold a written narration are counted and left
    alone - that file is the one artifact in a chapter that can't be rebuilt
    from anything else on disk. Replacing them is a single explicit answer
    (`--force`, or the confirmation this asks a real terminal) covering all
    of them, rather than one prompt per chapter."""
    from remanga.json_io import has_real_json_content
    from remanga.narration import BLANK, create_narration_file, narration_path
    from remanga.tui import confirm, is_interactive

    project = params["project"]
    chapters = split_chapters(params.get("chapters")) or discover_chapters(project)
    if not chapters:
        console.print(f"[yellow]Project '{project}' has no chapters yet - nothing to do.[/]")
        return

    # Three states, not two: a chapter with no file at all, one that already
    # holds the empty file this would write (nothing to do - rewriting zero
    # bytes over zero bytes is not work worth reporting), and one holding a
    # real script, which is the only case anybody has to decide about.
    paths = {chapter: narration_path(project, chapter) for chapter in chapters}
    written = {c for c, path in paths.items() if has_real_json_content(path)}
    already_blank = {c for c, path in paths.items() if c not in written and path.exists()}

    replace = bool(params.get("force"))
    if written and not replace:
        console.print(
            f"[yellow]{len(written)} chapter(s) already have a narration.json with content:[/] "
            f"{', '.join(c for c in chapters if c in written)}"
        )
        replace = is_interactive() and confirm(
            f"Blank those {len(written)} too?", default=False,
            note="their scripts can't be regenerated from anything else on disk",
        )

    targets = [c for c in chapters
               if c not in already_blank and (c not in written or replace)]
    if not targets:
        console.print(
            f"[dim]Nothing to write - {len(already_blank)} chapter(s) already have a blank "
            f"narration.json, {len(written)} have a written one.[/]"
        )
        return

    for chapter in targets:
        create_narration_file(project, chapter, mode=BLANK, force=True, quiet=True)
    kept = len(chapters) - len(targets)
    console.print(
        f"[bold green]✓ Blank narration.json written for {len(targets)} chapter(s)[/] "
        f"[dim](0 bytes each: {', '.join(targets)})[/]"
        + (f"\n[dim]{kept} chapter(s) already had one - left as they were.[/]" if kept else "")
    )


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
    chapters = split_chapters(params.get("chapters")) or discover_chapters(project)
    if not chapters:
        console.print(f"[yellow]Project '{project}' has no chapters yet - download some first.[/]")
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
    chapters = split_chapters(params.get("chapters")) or discover_chapters(project)
    if not chapters:
        console.print(f"[yellow]Project '{project}' has no chapters yet - nothing to look at.[/]")
        return

    launch_and_wait_all(project, chapters, config.marker, read_only=True)
    console.print("[bold green]✓ Viewer closed[/] [dim]- nothing was changed.[/]")
