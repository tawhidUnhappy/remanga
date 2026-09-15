"""Project-wide batch handlers: a chapter-by-chapter command run over every
chapter that's ready for it - blank narration files, cropping, packaging."""

from __future__ import annotations

from typing import Any

from remanga.commands.handlers.common import chosen_chapters
from remanga.config import RemangaConfig
from remanga.console import console


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
    chapters = chosen_chapters(params, "nothing to do")
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
    chapters = chosen_chapters(params, "nothing to crop")
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
    chapters = chosen_chapters(params, "nothing to package")
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
