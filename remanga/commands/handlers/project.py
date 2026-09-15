"""Handlers for the project-wide commands: whole-manga compilation, remix,
status, integrity verification, and the whole-project setup passes -
fetching every chapter, cropping and packaging every chapter that's ready
for it, and giving every chapter a narration file to fill in."""

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


def _chosen_chapters(params: dict[str, Any], otherwise: str) -> list[str]:
    """The chapters a whole-project command works on: --chapters when given,
    else every chapter the project has. Empty - and says so, ending with
    `otherwise` - when the project has none yet."""
    project = params["project"]
    chapters = split_chapters(params.get("chapters")) or discover_chapters(project)
    if not chapters:
        console.print(f"[yellow]Project '{project}' has no chapters yet - {otherwise}.[/]")
    return chapters


def _mangadex_listing(params: dict[str, Any], config: RemangaConfig, *, refresh: bool):
    """A downloader, and every chapter MangaDex lists for this project's manga
    with its local status - empty, and said so, when there are none in the
    configured language."""
    from remanga.downloader import MangaDexDownloader

    downloader = MangaDexDownloader(config.downloader)
    entries = downloader.list_chapters_with_status(params["project"], params.get("url"), force_refresh=refresh)
    if not entries:
        console.print(
            f"[yellow]MangaDex lists no chapters in '{config.downloader.language}' for this "
            f"manga - nothing to download.[/]"
        )
    return downloader, entries


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
    from remanga.tui import confirm, is_interactive

    project = params["project"]
    downloader, entries = _mangadex_listing(params, config, refresh=bool(params.get("refetch")))
    if not entries:
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


def download_range(params: dict[str, Any], config: RemangaConfig) -> None:
    """A run of chapters, downloaded - '1-5' is every chapter MangaDex lists
    numbered from 1 to 5, each decimal chapter a chapter of its own (1.1 and
    4.5 are in it, 5.1 comes after it), resolved by expand_chapter_selection.

    The listing is always fetched fresh rather than read from the 24h cache:
    a range is a question about which chapters exist, and a chapter
    published since yesterday is exactly the one somebody asks for. The
    range is asked for after that listing is shown, so the question comes
    with the answer's limits in front of it, and what it resolves to is
    shown before anything downloads.

    Chapters already downloaded go through download_chapter's re-verify:
    everything in pages/ that isn't one of the chapter's pages is removed,
    every page is checked against MangaDex's checksum, and only a page that
    fails is fetched again."""
    from remanga.full_recap.discovery import expand_chapter_selection
    from remanga.tui import ask_text, confirm, is_interactive

    project = params["project"]
    raw = (params.get("range") or "").strip()
    if not raw and not is_interactive():
        raise ValueError("--range is required when not running in an interactive terminal (e.g. --range 1-5).")

    downloader, entries = _mangadex_listing(params, config, refresh=True)
    if not entries:
        return
    available = [entry["chapter"] for entry in entries]
    downloaded = {entry["chapter"] for entry in entries if entry["status"] == "downloaded"}
    console.print(
        f"[bold]{len(available)} chapter(s)[/] on MangaDex in [bold]{config.downloader.language}[/]: "
        f"{available[0]} … {available[-1]} · [green]{len(downloaded)} already downloaded[/]"
    )

    if not raw:
        def check(text: str) -> str | None:
            try:
                return None if expand_chapter_selection(text, available, strict=True) else (
                    "No chapter on MangaDex falls in that range.")
            except ValueError as error:
                return str(error)

        raw = ask_text(
            "Chapters to download", allow_empty=False, validate=check,
            note="a range takes every chapter numbered from its start to its end - 1-5 includes 1.1 "
                 "and 4.5, not 5.1 · commas for more: 1-5,8,10-12",
        )
    chapters = expand_chapter_selection(raw, available, strict=True)
    if not chapters:
        console.print(f"[yellow]No chapter on MangaDex falls in '{raw}' - nothing to download.[/]")
        return

    have = [c for c in chapters if c in downloaded]
    console.print(
        f"[bold]{len(chapters)} chapter(s):[/] {', '.join(chapters)}\n"
        f"[dim]{len(chapters) - len(have)} to download · {len(have)} already here - re-verified page "
        f"by page, with anything in pages/ that isn't theirs removed[/]"
    )
    if is_interactive() and not confirm(
        f"Download these {len(chapters)} chapter(s)?", default=True,
        note="--force on the command line re-fetches every page clean instead",
    ):
        return
    downloader.download_chapters(project, chapters, params.get("url"), force=bool(params.get("force")))
    console.print(f"[bold green]✓ Chapters {raw}: all {len(chapters)} on disk and verified.[/]")


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
    chapters = _chosen_chapters(params, "nothing to do")
    if not chapters:
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


def crop_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """Crops every marked chapter in the project - the whole-project form of
    `crop`.

    Each chapter goes through crop_chapter_from_json with this project's
    cropper settings, the same call `crop` and the pipeline's crop step make.

    Chapters nobody has marked yet are skipped and named: in a project being
    worked through, those are simply the chapters not reached yet. Chapters
    already cropped are left alone, as `crop` leaves one alone - re-cropping
    wipes panels/ and cuts it again, so replacing them is one explicit answer
    covering all of them (`--force`, or the confirmation this asks a real
    terminal), never a prompt per chapter. A chapter that fails while
    cropping stops the run where it broke, same as download_chapters."""
    from remanga.cropper import CoordinateCropper
    from remanga.cropper.crop import cropped_panels
    from remanga.json_io import has_real_json_content
    from remanga.paths import get_chapter_dir
    from remanga.settings import package_summary
    from remanga.settings.project_prefs import cropper_config_for
    from remanga.tui import confirm, is_interactive

    project = params["project"]
    chapters = _chosen_chapters(params, "nothing to crop")
    if not chapters:
        return

    marked = [c for c in chapters if has_real_json_content(get_chapter_dir(project, c) / "crops.json")]
    unmarked = [c for c in chapters if c not in marked]
    if not marked:
        console.print(
            f"[yellow]None of the {len(chapters)} chapter(s) have been marked yet - "
            f"nothing to crop.[/] [dim]Run `mark-all` first.[/]"
        )
        return

    done = [c for c in marked if cropped_panels(project, c)]
    replace = bool(params.get("force"))
    if done and not replace:
        console.print(f"[yellow]{len(done)} chapter(s) are already cropped:[/] {', '.join(done)}")
        replace = is_interactive() and confirm(
            f"Re-crop those {len(done)} too?", default=False,
            note="their panels/ is wiped and cut again from crops.json",
        )

    kept = [] if replace else done
    notes = (
        (f"\n[dim]Already cropped, left as they were: {', '.join(kept)}[/]" if kept else "")
        + (f"\n[dim]Not marked yet, skipped: {', '.join(unmarked)}[/]" if unmarked else "")
    )
    targets = [c for c in marked if c not in kept]
    if not targets:
        console.print(f"[dim]Nothing to crop - every marked chapter is already cropped.[/]{notes}")
        return

    console.print(
        f"[bold]{len(targets)} chapter(s)[/] to crop"
        + (f" [dim]· {len(kept)} already cropped, left as they are[/]" if kept else "")
        + (f" [dim]· {len(unmarked)} not marked yet, skipped[/]" if unmarked else "")
    )
    cropper_config = cropper_config_for(config, project)
    cropper = CoordinateCropper(cropper_config)
    for i, chapter in enumerate(targets, start=1):
        console.print(f"[bold cyan]({i}/{len(targets)}) Chapter {chapter}[/]")
        cropper.crop_chapter_from_json(project, chapter, force=replace)

    formats = package_summary(cropper_config.package)
    console.print(
        f"[bold green]✓ Cropped {len(targets)} chapter(s)[/]{notes}"
        + (f"\n[dim]Run `package-all` to build the upload formats ({formats}).[/]"
           if formats != "panels only" else "")
    )


def package_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """Builds the chosen upload formats for every cropped chapter in the
    project - the whole-project form of `package`.

    Each chapter goes through package_chapter, the same one definition of
    packaging the `package` command and pipeline step use, so a chapter
    packaged here is packaged exactly the way it is there. The formats are
    asked once for the whole run, and remembered for the project the same
    way `package` remembers them.

    Chapters with no panels/ are counted and named rather than failed on:
    in a project being worked through, most of the uncropped chapters simply
    haven't been reached yet, and that's not an error worth stopping sixty
    chapters for. A chapter that fails while building still stops the run
    where it broke, same as download_chapters - a bulk run that looks
    finished but isn't is worse than one that stops."""
    from remanga.packaging import chapter_panels, package_chapter
    from remanga.settings import package_summary
    from remanga.settings.project_prefs import (
        active_package_formats,
        cropper_config_for,
        parse_package_formats,
        remember_package_formats,
    )

    project = params["project"]
    formats = parse_package_formats(params.get("formats"))
    chapters = _chosen_chapters(params, "nothing to package")
    if not chapters:
        return

    # Checked once here rather than left to package_chapter, which would say
    # "nothing to build" once per chapter.
    if not active_package_formats(config, project, formats):
        console.print(
            "[yellow]No package format selected - nothing to build.[/] "
            "[dim]Pick at least one format to package the chapters into.[/]"
        )
        return

    cropped = [c for c in chapters if chapter_panels(project, c)]
    uncropped = [c for c in chapters if c not in cropped]
    if not cropped:
        console.print(
            f"[yellow]None of the {len(chapters)} chapter(s) have been cropped yet - "
            f"nothing to package.[/] [dim]Run `crop` first.[/]"
        )
        return

    summary = package_summary(cropper_config_for(config, project, formats).package)
    console.print(
        f"[bold]{len(cropped)} cropped chapter(s)[/] to package · [cyan]{summary}[/]"
        + (f" [dim]· {len(uncropped)} not cropped yet, skipped[/]" if uncropped else "")
    )

    packaged: list[str] = []
    try:
        for i, chapter in enumerate(cropped, start=1):
            console.print(f"[bold cyan]({i}/{len(cropped)}) Chapter {chapter}[/]")
            package_chapter(config, project, chapter, formats)
            packaged.append(chapter)
    finally:
        # Remembered as soon as anything was built with it, even by a run
        # that stopped part-way: those chapters were built this way, and the
        # next run's checklist should open on the choice that built them.
        if packaged and formats is not None:
            remember_package_formats(project, formats)

    console.print(
        f"[bold green]✓ Packaged {len(packaged)} chapter(s)[/] [dim]({summary})[/]"
        + (f"\n[dim]Not cropped yet, skipped: {', '.join(uncropped)}[/]" if uncropped else "")
        + (f"\n[dim]Remembered for '{project}' - later chapters build the same.[/]"
           if formats is not None else "")
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
    chapters = _chosen_chapters(params, "download some first")
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
    chapters = _chosen_chapters(params, "nothing to look at")
    if not chapters:
        return

    launch_and_wait_all(project, chapters, config.marker, read_only=True)
    console.print("[bold green]✓ Viewer closed[/] [dim]- nothing was changed.[/]")
