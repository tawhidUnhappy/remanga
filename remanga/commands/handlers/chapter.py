"""Handlers for the per-chapter production commands - the download -> mark ->
crop -> write/review -> tts -> mix -> render path, plus the packaging and
whole-pipeline runners.

Every one of these is a thin wrapper around the same downloader/cropper/
audio/video/webui call the CLI has always made, uniform in shape
(handler(params, config)) so both front-ends can invoke them identically."""

from __future__ import annotations

from typing import Any, Dict

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.pipeline import load_pipeline, run_pipeline
from remanga.settings import package_summary
from remanga.settings.project_prefs import (
    cropper_config_for, parse_package_formats, remember_package_formats,
)
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker
from remanga.webui import launch_and_wait_writer


def download(params: Dict[str, Any], config: RemangaConfig) -> None:
    MangaDexDownloader(config.downloader).download_chapter(
        params.get("url"), params["chapter"], params["project"]
    )


def mark(params: Dict[str, Any], config: RemangaConfig) -> None:
    launch_panel_marker(params["project"], params["chapter"], config.marker)


def write(params: Dict[str, Any], config: RemangaConfig) -> None:
    launch_and_wait_writer(params["project"], params["chapter"], config.writer, config.ocr)


def review(params: Dict[str, Any], config: RemangaConfig) -> None:
    # Deferred import: the wizard imports the command registry, so a
    # top-level import of it here would be circular.
    from remanga.wizard import run_narration_review_loop

    run_narration_review_loop(params["project"], params["chapter"], config)


def crop(params: Dict[str, Any], config: RemangaConfig) -> None:
    """Crops, then packages whatever formats are active for this project -
    the ones chosen the last time `package` ran here, falling back to
    config.json's global switches (see settings/project_prefs.py)."""
    project = params["project"]
    CoordinateCropper(cropper_config_for(config, project)).crop_chapter_from_json(
        project, params["chapter"], force=bool(params.get("force"))
    )


def package(params: Dict[str, Any], config: RemangaConfig) -> None:
    """Builds the chosen package formats from an already-cropped chapter's
    panels/.

    Deliberately separate from `crop` (which only tops a format up if it's
    missing entirely - see CoordinateCropper's resume check): this rebuilds
    what you ask for, right after deciding you want it.

    `--formats` (the wizard offers it as a checklist of every format) picks
    what to build for this run, and that choice is then remembered for the
    project - so the next chapter builds the same thing without asking. With
    no --formats, it builds whatever this project already chose, or
    config.json's switches if it never has."""
    from remanga.cropper.crop_report import package_outputs
    from remanga.paths import get_chapter_dir

    project_name, chapter_num = params["project"], params["chapter"]
    panels_dir = get_chapter_dir(project_name, chapter_num) / "panels"
    panel_paths = sorted(p for p in panels_dir.iterdir() if p.is_file()) if panels_dir.exists() else []
    if not panel_paths:
        raise FileNotFoundError(
            f"No cropped panels found for chapter {chapter_num}: {panels_dir}\n"
            f"Run `crop` for this chapter first."
        )

    formats = parse_package_formats(params.get("formats"))
    cropper = cropper_config_for(config, project_name, formats)
    active = package_summary(cropper.package)
    if active == "panels only":
        console.print(
            "[yellow]No package format selected - nothing to build.[/] "
            "[dim]panels/ already exists; pick at least one format to package it into.[/]"
        )
        return

    console.print(f"[cyan]Building:[/] {active}")
    package_outputs(cropper, panel_paths, project_name, chapter_num)

    if formats is not None:
        remember_package_formats(project_name, formats)
        console.print(f"[dim]Remembered for '{project_name}' - the next chapter builds the same.[/]")


def tts(params: Dict[str, Any], config: RemangaConfig) -> None:
    TTSEngine(config.tts, config.audio).generate_narration_audio(
        params["project"], params["chapter"],
        voice_override=params.get("voice"), interactive=True, force=bool(params.get("force")),
    )


def mix(params: Dict[str, Any], config: RemangaConfig) -> None:
    AudioProcessor(config.audio).mix_master_audio(
        params["project"], params["chapter"], bgm_override=params.get("bgm"), interactive=True
    )


def render(params: Dict[str, Any], config: RemangaConfig) -> None:
    VideoRenderer(config.system, config.video).render_video(
        params["project"], params["chapter"], force=bool(params.get("force"))
    )


def run(params: Dict[str, Any], config: RemangaConfig) -> None:
    """Runs this project's pipeline.json, or an explicit --steps override."""
    steps_raw = params.get("steps")
    steps = [s.strip() for s in steps_raw.split(",") if s.strip()] if steps_raw else load_pipeline(params["project"])
    run_pipeline(params["project"], params["chapter"], config, steps)
