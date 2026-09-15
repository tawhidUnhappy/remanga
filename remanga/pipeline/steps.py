"""The core pipeline steps' work. Each is a thin wrapper around the exact same
downloader/cropper/audio/video/webui call (and, for narration/review, the
exact same remanga/wizard/ function) the interactive wizard has always used,
including their console messages."""

from __future__ import annotations

from pathlib import Path

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, display_path, print_path
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.json_io import has_real_json_content
from remanga.packaging import package_chapter
from remanga.paths import get_chapter_dir
from remanga.settings.project_prefs import cropper_config_for
from remanga.tui import is_interactive
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker


def run_download(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print(f"[bold]Step — Downloading Chapter {chapter}[/]")
    dl = MangaDexDownloader(config.downloader)
    # None -> MangaDexDownloader.download_chapter falls back to this
    # project's saved manga_url/manga_id (project.json) - the wizard writes
    # that field before calling into the pipeline (see remanga/wizard/), and every
    # subsequent run reuses it the same way `remanga download` without --url
    # already does.
    dl.download_chapter(None, chapter, project)


def run_mark(project: str, chapter: str, config: RemangaConfig) -> None:
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


def run_crop(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print("\n[bold]Step — Cropping Panels[/]")
    CoordinateCropper(cropper_config_for(config, project)).crop_chapter_from_json(project, chapter)


def run_package(project: str, chapter: str, config: RemangaConfig) -> None:
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


def run_init_narration(project: str, chapter: str, config: RemangaConfig) -> None:
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


def run_pause(project: str, chapter: str, config: RemangaConfig) -> None:
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
    # imports run_pipeline from this package.
    from remanga.wizard.handoff import pause
    pause("Press Enter to continue")


def run_narration(project: str, chapter: str, config: RemangaConfig) -> None:
    # Deferred import: remanga/wizard/ imports run_pipeline/load_pipeline from this
    # package for its own "run everything" path, so a top-level import here
    # would be circular. Only resolved at call time, same trick remanga/reset/'s
    # "remark" restart path already uses for launch_panel_marker.
    from remanga.wizard import run_narration_step
    run_narration_step(project, chapter, config)


def run_review(project: str, chapter: str, config: RemangaConfig) -> None:
    from remanga.wizard import run_narration_review_loop
    run_narration_review_loop(project, chapter, config)


def run_tts(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print(f"\n[bold]Step — Synthesizing Vocal Audio via {config.tts.spec.display_name}[/]")
    tts = TTSEngine(config.tts, config.audio)
    tts.generate_narration_audio(project, chapter, interactive=True)


def run_mix(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print("\n[bold]Step — Mixing Master Audio Track[/]")
    mixer = AudioProcessor(config.audio)
    mixer.mix_master_audio(project, chapter, interactive=True)


def run_render(project: str, chapter: str, config: RemangaConfig) -> None:
    console.print(f"\n[bold]Step — Rendering Final {config.video.height}p Recap Video[/]")
    renderer = VideoRenderer(config.system, config.video)
    final_video = renderer.render_video(project, chapter)
    console.print(
        f"\n[bold green]✓ Recap video complete[/] "
        f"[dim]({config.video.width}x{config.video.height}, {config.video.background_style.title()} canvas)[/]"
    )
    print_path(f"  {display_path(final_video, wrap=False)}")
