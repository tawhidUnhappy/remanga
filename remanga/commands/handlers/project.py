"""Handlers for the project-wide commands: whole-manga compilation, remix,
status and integrity verification."""

from __future__ import annotations

from typing import Any, Dict

from remanga.commands.selection import split_chapters
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.full_recap import FullRecapCompiler
from remanga.remix import remix_project
from remanga.status import render_status_panel
from remanga.verify import verify_project


def full_recap(params: Dict[str, Any], config: RemangaConfig) -> None:
    FullRecapCompiler(config).compile_full_manga(
        params["project"], force=bool(params.get("force")),
        chapters=split_chapters(params.get("chapters")),
    )


def remix(params: Dict[str, Any], config: RemangaConfig) -> None:
    remix_project(
        params["project"], config, chapters=split_chapters(params.get("chapters")),
        bgm_override=params.get("bgm"), rejoin=not params.get("no_rejoin"),
    )


def status(params: Dict[str, Any], config: RemangaConfig) -> None:
    console.print(render_status_panel(params["project"], params["chapter"]))


def verify(params: Dict[str, Any], config: RemangaConfig) -> None:
    verify_project(
        params["project"], chapters=split_chapters(params.get("chapters")),
        check_video=not params.get("no_video"),
    )
