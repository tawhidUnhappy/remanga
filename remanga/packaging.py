"""Packaging a chapter's cropped panels into the upload formats.

One function, used by both callers - the `package` command and the
`package` pipeline step - so "what does packaging a chapter mean" has a
single definition. Cropping deliberately does NOT call this: `crop` cuts
panels and stops, because building a 30MB zip nobody asked for as a side
effect of cropping is the kind of thing that's only ever noticed when it
wastes a minute and a gigabyte. Packaging is its own step, run when you
want it."""

from __future__ import annotations

from typing import List, Optional, Sequence

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.paths import get_chapter_dir, load_project_metadata
from remanga.settings import package_summary
from remanga.settings.project_prefs import cropper_config_for, remember_package_formats


def chapter_panels(project_name: str, chapter_num: str) -> List:
    """Every cropped panel file for this chapter, in order. Empty when the
    chapter hasn't been cropped yet."""
    panels_dir = get_chapter_dir(project_name, chapter_num) / "panels"
    if not panels_dir.exists():
        return []
    return sorted(p for p in panels_dir.iterdir() if p.is_file())


def package_chapter(
    config: RemangaConfig,
    project_name: str,
    chapter_num: str,
    formats: Optional[Sequence[str]] = None,
    *,
    remember: bool = False,
    required: bool = True,
) -> bool:
    """Builds this chapter's active upload formats from its panels/.

    `formats` is this run's explicit answer (None = use the project's
    remembered choice, else config.json's switches - see
    settings/project_prefs.py). `remember=True` stores an explicit choice on
    the project so later chapters build the same set unasked.

    `required=False` makes a chapter with no panels a no-op rather than an
    error, for the pipeline step - where a missing crop is already the crop
    step's business to report. Returns whether anything was built."""
    from remanga.cropper.crop_report import package_outputs

    panel_paths = chapter_panels(project_name, chapter_num)
    if not panel_paths:
        message = (
            f"No cropped panels found for chapter {chapter_num}: "
            f"{get_chapter_dir(project_name, chapter_num) / 'panels'}\n"
            f"Run `crop` for this chapter first."
        )
        if required:
            raise FileNotFoundError(message)
        console.print(f"[yellow]Nothing to package for chapter {chapter_num} - not cropped yet.[/]")
        return False

    # reading_direction ends up in every bundle's chapter_info.json via
    # chapter_identity_fields (see remanga.paths.metadata), so it's required
    # here - and only here. Cropping never needed it; it used to be checked
    # there purely because cropping also packaged. The wizard asks once per
    # project (or derives it from MangaDex), so this only ever fires for a
    # scripted run against a project that has never been through it.
    if "reading_direction" not in load_project_metadata(project_name):
        raise ValueError(
            f"Missing 'reading_direction' for project '{project_name}' - required before "
            f"panels_pdf/panels_zip/sheets_zip can be packaged. Run `remanga interactive` once "
            f"for this project (it asks and saves it), or add \"reading_direction\": "
            f"\"right_to_left\" (or \"left_to_right\") to projects/{project_name}/project.json."
        )

    cropper = cropper_config_for(config, project_name, formats)
    active = package_summary(cropper.package)
    if active == "panels only":
        console.print(
            "[yellow]No package format selected - nothing to build.[/] "
            "[dim]panels/ already exists; pick at least one format to package it into.[/]"
        )
        return False

    console.print(f"[cyan]Building:[/] {active}")
    package_outputs(cropper, panel_paths, project_name, chapter_num)

    if remember and formats is not None:
        remember_package_formats(project_name, formats)
        console.print(f"[dim]Remembered for '{project_name}' - the next chapter builds the same.[/]")
    return True
