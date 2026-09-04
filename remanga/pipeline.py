"""Modular step-registry + JSON pipeline config: the download -> mark ->
crop -> package -> narration -> review -> tts -> mix -> render -> youtube sequence, now expressed as an ordered list of named, independently
runnable steps instead of one hardcoded function. This lets a caller run
"just one tool" (a single step name), "a lot of them" (an arbitrary subset,
in any order), or the full default pipeline - driven by
projects/<name>/pipeline.json instead of code.

Each step's actual work is NOT reimplemented here - every _run_* function
below is a thin wrapper around the exact same downloader/cropper/audio/video/
webui calls (and, for narration/review/youtube, the exact same remanga/wizard/ functions)
the interactive wizard has always used, including their console messages -
so the default step list run through run_pipeline() behaves identically to
today's wizard. The wizard's own "run the pipeline" path is just the `run`
command, which calls run_pipeline(project, chapter, config, load_pipeline(project))."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, display_path, print_path
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.json_io import has_real_json_content, read_json_or, write_json
from remanga.packaging import package_chapter
from remanga.paths import get_chapter_dir, get_pipeline_path
from remanga.settings.project_prefs import cropper_config_for
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker


@dataclass
class Step:
    """One pipeline step. `run` takes (project, chapter, config) - the same
    signature for every step, regardless of what extra state a given step
    happens to need (e.g. download resolves its own manga URL from
    project.json, same fallback MangaDexDownloader.download_chapter already
    has). `needs` is informational only - the prior step names this one
    normally expects to have already run - used for a soft warning in
    run_pipeline, not a real dependency-graph resolver."""
    name: str
    description: str
    run: Callable[[str, str, RemangaConfig], None]
    needs: List[str] = field(default_factory=list)


def _run_download(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print(f"[bold]Step — Downloading Chapter {chapter}[/]")
    dl = MangaDexDownloader(config.downloader)
    # None -> MangaDexDownloader.download_chapter falls back to this
    # project's saved manga_url/manga_id (project.json) - the wizard writes
    # that field before calling into the pipeline (see remanga/wizard/), and every
    # subsequent run reuses it the same way `remanga download` without --url
    # already does.
    dl.download_chapter(None, chapter, project)


def _run_mark(project: str, chapter: str, config: RemangaConfig) -> None:
    chap_dir = get_chapter_dir(project, chapter)
    crops_path = chap_dir / "crops.json"
    if has_real_json_content(crops_path):
        return
    console.print(
        "\n[bold]Mark Panels[/]\n"
        "Opening the Panel Marker web UI. Mark each panel on every story page "
        f"(MAGI v3 pre-fills what it can find), then press "
        f"{'⌘S' if config.marker.auto_open_browser else 'Ctrl+S'} or click "
        "Save & Continue in the browser tab.\n"
    )
    launch_panel_marker(project, chapter, config.marker)
    console.print("[green]✓ Panels marked and crops.json saved.[/]")


def _run_crop(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print("\n[bold]Step — Cropping Panels[/]")
    CoordinateCropper(cropper_config_for(config, project)).crop_chapter_from_json(project, chapter)


def _run_package(project: str, chapter: str, config: RemangaConfig) -> None:
    """Builds this project's chosen upload formats. Its own step, because
    cropping no longer packages as a side effect (see remanga/cropper/
    crop.py) - so a pipeline that doesn't want a 30MB zip built every run
    simply leaves this step out."""
    console.print("\n[bold]Step — Packaging Vision Uploads[/]")
    package_chapter(config, project, chapter, required=False)


def _run_narration(project: str, chapter: str, config: RemangaConfig) -> None:
    # Deferred import: remanga/wizard/ imports run_pipeline/load_pipeline from this
    # module for its own "run everything" path, so a top-level import here
    # would be circular. Only resolved at call time, same trick remanga/reset/'s
    # "remark" restart path already uses for launch_panel_marker.
    from remanga.wizard import run_narration_step
    run_narration_step(project, chapter, config)


def _run_review(project: str, chapter: str, config: RemangaConfig) -> None:
    from remanga.wizard import run_narration_review_loop
    run_narration_review_loop(project, chapter, config)


def _run_tts(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print("\n[bold]Step — Synthesizing Vocal Audio via IndexTTS-2.5[/]")
    tts = TTSEngine(config.tts, config.audio)
    tts.generate_narration_audio(project, chapter, interactive=True)


def _run_mix(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print("\n[bold]Step — Mixing Master Audio Track[/]")
    mixer = AudioProcessor(config.audio)
    mixer.mix_master_audio(project, chapter, interactive=True)


def _run_render(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print(f"\n[bold]Step — Rendering Final {config.video.height}p Recap Video[/]")
    renderer = VideoRenderer(config.system, config.video)
    final_video = renderer.render_video(project, chapter)
    console.print(
        f"\n[bold green]✓ Recap video complete[/] "
        f"[dim]({config.video.width}x{config.video.height}, {config.video.background_style.title()} canvas)[/]"
    )
    print_path(f"  {display_path(final_video, wrap=False)}")


def _run_youtube(project: str, chapter: str, config: RemangaConfig) -> None:
    """The publishing hand-off: title, description, tags and thumbnail brief
    for the video the render step just produced. Deferred import for the same
    reason narration/review use one - remanga/wizard/ imports run_pipeline
    from this module."""
    from remanga.wizard import run_youtube_metadata_step
    run_youtube_metadata_step(project, chapter, config)


# Ordered, once - both STEP_REGISTRY (source of truth for what a step is/
# does) and DEFAULT_STEPS (today's exact hardcoded wizard order, used as the
# fallback whenever a project has no pipeline.json) come from this one list.
STEP_REGISTRY: List[Step] = [
    Step("download", "Download chapter pages from MangaDex", _run_download),
    Step("mark", "Mark panels via the Panel Marker web UI (writes crops.json)", _run_mark, needs=["download"]),
    Step("crop", "Crop panels out of the marked pages", _run_crop, needs=["mark"]),
    Step("package", "Package the panels into the chosen upload formats (sheets/zips/PDF)",
         _run_package, needs=["crop"]),
    Step("narration", "Write narration.json + memory.json via LLM copy/paste", _run_narration,
         needs=["package"]),
    Step("review", "Review narration via the Narration Reviewer web UI", _run_review, needs=["narration"]),
    Step("tts", "Synthesize vocal audio via TTS", _run_tts, needs=["review"]),
    Step("mix", "Mix master audio track (narration + BGM + loudnorm)", _run_mix, needs=["tts"]),
    Step("render", "Render the final recap video", _run_render, needs=["mix"]),
    Step("youtube", "Write the YouTube title/description/thumbnail brief via LLM copy/paste "
                    "(writes youtube.json)", _run_youtube, needs=["render"]),
]

_STEP_BY_NAME = {step.name: step for step in STEP_REGISTRY}
DEFAULT_STEPS: List[str] = [step.name for step in STEP_REGISTRY]


def run_pipeline(project: str, chapter: str, config: RemangaConfig, steps: Optional[List[str]] = None) -> None:
    """Runs the named steps, in the given order. `steps` defaults to
    DEFAULT_STEPS (today's exact wizard sequence). An unknown step name is
    warned about and skipped, not fatal - a typo in pipeline.json shouldn't
    abort every other step in it."""
    step_names = list(steps) if steps is not None else list(DEFAULT_STEPS)
    for name in step_names:
        step = _STEP_BY_NAME.get(name)
        if step is None:
            console.print(f"[bold yellow]⚠ Unknown pipeline step '{name}' - skipping.[/]")
            continue
        step.run(project, chapter, config)


def load_pipeline(project: str) -> List[str]:
    """Reads projects/<name>/pipeline.json's ordered "steps" list. Falls back
    to DEFAULT_STEPS - unchanged - whenever the file is missing, empty, or
    malformed, so an existing project with no pipeline.json keeps running
    today's exact step order with zero behavior change."""
    data = read_json_or(get_pipeline_path(project), {})
    steps = data.get("steps") if isinstance(data, dict) else None
    if isinstance(steps, list) and steps:
        return [str(s) for s in steps]
    return list(DEFAULT_STEPS)


def ensure_pipeline_file(project: str) -> Path:
    """Writes the default pipeline.json for a project the first time it's
    touched, without ever clobbering one a user already customized - mirrors
    remanga.paths.ensure_memory_file/ensure_global_lessons_file."""
    path = get_pipeline_path(project)
    if not path.exists():
        write_json(path, {"steps": list(DEFAULT_STEPS)})
    return path
