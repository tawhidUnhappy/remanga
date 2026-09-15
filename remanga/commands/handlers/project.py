"""Handlers for the project-wide commands: whole-manga compilation, remix,
status and integrity verification here; the whole-project setup passes in
modules of their own - fetching chapters (project_downloads.py), running
narration-init/crop/package over every chapter (project_batches.py), and the
marker sessions (project_marker.py). Those are re-exported below, since this
module is where the command catalog looks every project handler up."""

from __future__ import annotations

from typing import Any

from remanga.commands.handlers.project_batches import crop_all, narration_init_all, package_all
from remanga.commands.handlers.project_downloads import download_all, download_range
from remanga.commands.handlers.project_marker import mark_all, view_marks
from remanga.commands.selection import split_chapters
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.full_recap import FullRecapCompiler
from remanga.remix import remix_project
from remanga.reset import DEFAULT_REBUILD_MODE, REBUILD_MODE_BY_NAME
from remanga.status import render_status_panel
from remanga.verify import verify_project

__all__ = [
    "crop_all",
    "download_all",
    "download_range",
    "full_recap",
    "mark_all",
    "narration_init_all",
    "package_all",
    "remix",
    "status",
    "verify",
    "view_marks",
]


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
