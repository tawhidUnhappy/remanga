"""Handlers for the per-chapter production commands - the download -> mark ->
crop -> write/review -> tts -> mix -> render path, plus the packaging and
whole-pipeline runners.

Every one of these is a thin wrapper around the same downloader/cropper/
audio/video/webui call the CLI has always made, uniform in shape
(handler(params, config)) so both front-ends can invoke them identically."""

from __future__ import annotations

from typing import Any

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.full_recap.discovery import expand_chapter_selection
from remanga.narration import TEMPLATE, create_narration_file
from remanga.packaging import package_chapter
from remanga.pipeline import load_pipeline, run_pipeline
from remanga.settings.project_prefs import cropper_config_for, parse_package_formats
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker, launch_and_wait_writer


def download(params: dict[str, Any], config: RemangaConfig) -> None:
    MangaDexDownloader(config.downloader).download_chapter(
        params.get("url"), params["chapter"], params["project"]
    )


def download_chapters(params: dict[str, Any], config: RemangaConfig) -> None:
    """Download several chapters at once - a comma list and/or numeric
    ranges ('1,3,7-9'), 'all' for every chapter MangaDex has, or (the
    common case, and the only option when --chapters is left unset from an
    interactive terminal) the picker screen showing which chapters this
    project already has - see remanga/wizard/downloads.py."""
    project = params["project"]
    manga_id_or_url = params.get("url")
    raw_chapters = (params.get("select") or "").strip()
    force = bool(params.get("force"))
    refetch = bool(params.get("refetch"))

    if not raw_chapters:
        from remanga.tui import is_interactive
        from remanga.wizard.downloads import run_download_chapters

        if not is_interactive():
            raise ValueError(
                "--select is required when not running in an interactive terminal "
                "(a comma list and/or ranges like '1,3,7-9', or 'all')."
            )
        run_download_chapters(project, config, manga_id_or_url)
        return

    downloader = MangaDexDownloader(config.downloader)
    entries = downloader.list_chapters_with_status(project, manga_id_or_url, force_refresh=refetch)
    available = [e["chapter"] for e in entries]
    chapter_nums = (available if raw_chapters.lower() == "all"
                    else expand_chapter_selection(raw_chapters, available, strict=True))

    if not chapter_nums:
        console.print("[yellow]No chapters matched that selection - nothing to download.[/]")
        return

    downloader.download_chapters(project, chapter_nums, manga_id_or_url, force=force)


def mark(params: dict[str, Any], config: RemangaConfig) -> None:
    launch_panel_marker(params["project"], params["chapter"], config.marker)


def narration_init(params: dict[str, Any], config: RemangaConfig) -> None:
    """Creates the chapter's narration.json - a full per-panel template, or a
    genuinely empty file. See remanga/narration.py for what each mode
    writes and why both exist."""
    create_narration_file(
        params["project"], params["chapter"],
        mode=params.get("mode") or TEMPLATE, force=bool(params.get("force")),
    )


def write(params: dict[str, Any], config: RemangaConfig) -> None:
    launch_and_wait_writer(params["project"], params["chapter"], config.writer, config.ocr)


def review(params: dict[str, Any], config: RemangaConfig) -> None:
    # Deferred import: the wizard imports the command registry, so a
    # top-level import of it here would be circular.
    from remanga.wizard import run_narration_review_loop

    run_narration_review_loop(params["project"], params["chapter"], config)


def crop(params: dict[str, Any], config: RemangaConfig) -> None:
    """Cuts the panels, and only that - packaging is `package`'s job."""
    from remanga.settings import package_summary

    project, chapter = params["project"], params["chapter"]
    CoordinateCropper(cropper_config_for(config, project)).crop_chapter_from_json(
        project, chapter, force=bool(params.get("force"))
    )
    formats = package_summary(cropper_config_for(config, project).package)
    if formats != "panels only":
        console.print(f"[dim]Run `package` to build the upload formats ({formats}).[/]")


def package(params: dict[str, Any], config: RemangaConfig) -> None:
    """Builds the chosen upload formats from an already-cropped chapter's
    panels/ - the only thing that packages a chapter (`crop` cuts panels and
    stops; see remanga/packaging.py).

    `--formats` (a checklist in the wizard) picks what to build for this run,
    and that choice is then remembered for the project, so the next chapter
    builds the same thing without asking. With no --formats, it builds
    whatever the project already chose, or config.json's switches if it
    never has."""
    package_chapter(
        config, params["project"], params["chapter"],
        parse_package_formats(params.get("formats")), remember=True,
    )


def tts(params: dict[str, Any], config: RemangaConfig) -> None:
    """Synthesizes this chapter's narration. `--engine` swaps the engine for
    this run only - config.json keeps whatever it says, since a one-off
    "try the other voice model on this chapter" shouldn't silently redefine
    what every later run does."""
    tts_config = config.tts
    engine = params.get("engine")
    if engine and engine != config.tts.engine:
        tts_config = config.tts.model_copy(deep=True)
        tts_config.engine = engine
        console.print(
            f"[cyan]Synthesizing with {tts_config.spec.display_name} for this run[/] "
            f"[dim](config.json still says {config.tts.spec.display_name})[/]"
        )

    TTSEngine(tts_config, config.audio).generate_narration_audio(
        params["project"], params["chapter"],
        voice_override=params.get("voice"), interactive=True, force=bool(params.get("force")),
    )


def mix(params: dict[str, Any], config: RemangaConfig) -> None:
    AudioProcessor(config.audio).mix_master_audio(
        params["project"], params["chapter"], bgm_override=params.get("bgm"), interactive=True
    )


def render(params: dict[str, Any], config: RemangaConfig) -> None:
    VideoRenderer(config.system, config.video).render_video(
        params["project"], params["chapter"], force=bool(params.get("force"))
    )


def run(params: dict[str, Any], config: RemangaConfig) -> None:
    """Runs this project's pipeline.json, or an explicit --steps override."""
    steps_raw = params.get("steps")
    steps = [s.strip() for s in steps_raw.split(",") if s.strip()] if steps_raw else load_pipeline(params["project"])
    run_pipeline(params["project"], params["chapter"], config, steps)
