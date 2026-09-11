"""Modular step-registry + JSON pipeline config: the download -> mark ->
crop -> package -> narration -> review -> tts -> mix -> render sequence,
now expressed as an ordered list of named, independently runnable steps
instead of one hardcoded function. This lets a caller run
"just one tool" (a single step name), "a lot of them" (an arbitrary subset,
in any order), or the full default pipeline - driven by the project's own
saved step list (project.json's "pipeline") instead of code.

Each step's actual work is NOT reimplemented here - every _run_* function
below is a thin wrapper around the exact same downloader/cropper/audio/video/
webui calls (and, for narration/review, the exact same remanga/wizard/ functions)
the interactive wizard has always used, including their console messages -
so the default step list run through run_pipeline() behaves identically to
today's wizard. The wizard's own "run the pipeline" path is just the `run`
command, which calls run_pipeline(project, chapter, config, load_pipeline(project))."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, display_path, print_path
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.json_io import has_real_json_content, read_json_or
from remanga.packaging import package_chapter
from remanga.paths import get_chapter_dir, get_pipeline_path
from remanga.settings.project_prefs import cropper_config_for, remembered_pipeline
from remanga.tui import is_interactive
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
    needs: list[str] = field(default_factory=list)


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
        f"(or press Detect to have MAGI v3 find them), then press "
        f"{'⌘S' if config.marker.auto_open_browser else 'Ctrl+S'} or click "
        "Save in the browser tab.\n"
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


def _replacing_narration_ok(path: Path, chapter: str) -> bool:
    """Whether to blank a narration.json that already has a script in it.

    Its own function so the question is asked in exactly one place, and so
    the non-interactive answer is unmistakably no: a piped or scripted run
    has nobody to ask, and "nobody answered" must never be read as consent
    to delete the one file in a chapter that can't be rebuilt from anything
    else on disk."""
    from remanga.tui import confirm

    if not is_interactive():
        return False
    return confirm(
        f"Chapter {chapter} already has a narration.json - replace it with an empty file?",
        default=False,
        note=f"{display_path(path, wrap=False)} · the script in it can't be regenerated "
             "from anything else on disk",
    )


def _run_init_narration(project: str, chapter: str, config: RemangaConfig) -> None:
    """Puts this chapter's narration.json on disk as a genuinely empty file -
    zero bytes, not "{}", not "[]", nothing at all - so the script has a
    place to be written into before anything tries to write it.

    Zero bytes is the placeholder state the rest of remanga already
    understands. Every "has this chapter been narrated yet?" question is
    answered by size (json_io.has_real_json_content), so an empty
    narration.json is read as "not written yet" by the status panel, by
    verify, and by the `narration` step - the file exists, the chapter is
    still honestly unnarrated, and nothing downstream is fooled into
    thinking there is a script here. That is what makes this safe as a
    normal stage rather than a special one: it reserves the path and changes
    no other step's mind about anything.

    A chapter that already has a script is never blanked on the way past.
    That file is the one artifact in a chapter that can't be regenerated
    from anything else on disk - not from the pages, not from the panels,
    not from any setting - so replacing it is a question, asked with "keep
    it" as the answer Enter gives, and only ever asked to a real terminal:
    a piped or scripted run keeps the file and says so, because there is
    nobody there to say no."""
    from remanga.narration import BLANK, create_narration_file, narration_path

    path = narration_path(project, chapter)
    if has_real_json_content(path) and not _replacing_narration_ok(path, chapter):
        console.print(f"[dim]Narration — kept chapter {chapter}'s existing narration.json.[/]")
        return
    # create_narration_file reports what it wrote and where, the same way it
    # does for the `narration-init` command - repeating the path here would
    # print it twice. force, because the only way past the guard above is a
    # yes to replacing what's there.
    console.print("\n[bold]Step — Creating narration.json[/]")
    create_narration_file(project, chapter, mode=BLANK, force=True)


def _run_pause(project: str, chapter: str, config: RemangaConfig) -> None:
    """A stage that does nothing but stop, until Enter.

    Every other step in this registry runs something. This one is a
    placeholder in the literal sense - it holds a place in the order for
    work that isn't remanga's: filling in the narration.json that
    `init-narration` just left empty, dropping a file into the chapter
    folder, checking a panel crop by eye. Without it, "let the pipeline get
    this far, then let me do a thing, then let it carry on" means running
    two pipelines and remembering where the seam was.

    So it prints the chapter folder (the thing you're most likely about to
    open) and waits. Enter continues to the next stage; there's nothing to
    answer and nothing to get wrong.

    A non-interactive run doesn't wait: there is no one to press Enter, and
    a piped `run` blocking forever on stdin - or dying on EOFError - would
    turn a checkpoint into a hang."""
    console.print(f"\n[bold]Step — Paused before the next stage[/] [dim](chapter {chapter})[/]")
    print_path(f"  {display_path(get_chapter_dir(project, chapter), wrap=False)}")
    if not is_interactive():
        console.print("[dim]Not an interactive terminal - continuing without waiting.[/]")
        return
    # Deferred for the same reason narration/review are: remanga/wizard/
    # imports run_pipeline from this module.
    from remanga.wizard.handoff import pause
    pause("Press Enter to continue")


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
    console.print("\n[bold]Step — Synthesizing Vocal Audio via Kokoro-82M[/]")
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


# Ordered, once - both STEP_REGISTRY (source of truth for what a step is/
# does) and DEFAULT_STEPS (today's exact hardcoded wizard order, used as the
# fallback whenever a project has never chosen) come from this one list.
STEP_REGISTRY: list[Step] = [
    Step("download", "Download chapter pages from MangaDex", _run_download),
    Step("mark", "Mark panels via the Panel Marker web UI (writes crops.json)", _run_mark, needs=["download"]),
    Step("crop", "Crop panels out of the marked pages", _run_crop, needs=["mark"]),
    Step("package", "Package the panels into the chosen upload formats (sheets/zips/PDF)",
         _run_package, needs=["crop"]),
    Step("init-narration",
         "Create a completely empty narration.json - zero bytes, not even {} - for the script "
         "to be written into",
         _run_init_narration),
    Step("pause", "Wait for Enter before going on - room to fill something in by hand first",
         _run_pause),
    Step("narration", "Write narration.json + memory.json via LLM copy/paste", _run_narration,
         needs=["package"]),
    Step("review", "Review narration via the Narration Reviewer web UI", _run_review, needs=["narration"]),
    Step("tts", "Synthesize vocal audio via TTS", _run_tts, needs=["review"]),
    Step("mix", "Mix master audio track (narration + BGM + loudnorm)", _run_mix, needs=["tts"]),
    Step("render", "Render the final recap video", _run_render, needs=["mix"]),
]

_STEP_BY_NAME = {step.name: step for step in STEP_REGISTRY}
DEFAULT_STEPS: list[str] = [step.name for step in STEP_REGISTRY]


def run_pipeline(project: str, chapter: str, config: RemangaConfig, steps: list[str] | None = None) -> None:
    """Runs the named steps, in the given order. `steps` defaults to
    DEFAULT_STEPS (today's exact wizard sequence). An unknown step name is
    warned about and skipped, not fatal - a typo in a saved step list
    shouldn't abort every other step in it."""
    step_names = list(steps) if steps is not None else list(DEFAULT_STEPS)
    for name in step_names:
        step = _STEP_BY_NAME.get(name)
        if step is None:
            console.print(f"[bold yellow]⚠ Unknown pipeline step '{name}' - skipping.[/]")
            continue
        step.run(project, chapter, config)


def load_pipeline(project: str) -> list[str]:
    """This project's ordered step list: project.json's "pipeline", else a
    legacy pipeline.json if the project still has one, else DEFAULT_STEPS -
    so a project that has never chosen runs today's exact order, unchanged.

    The steps moved into project.json to sit with everything else a project
    remembers (see remanga.settings.project_prefs); the fallback below is what
    keeps a project written by an older version running until its next save
    moves it across."""
    steps = remembered_pipeline(project)
    if steps:
        return steps
    legacy = read_json_or(get_pipeline_path(project), {})
    steps = legacy.get("steps") if isinstance(legacy, dict) else None
    if isinstance(steps, list) and steps:
        return [str(s) for s in steps]
    return list(DEFAULT_STEPS)
