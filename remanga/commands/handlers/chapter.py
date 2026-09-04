"""Handlers for the per-chapter production commands - the download -> mark ->
crop -> write/review -> tts -> mix -> render path, plus the packaging and
whole-pipeline runners.

Every one of these is a thin wrapper around the same downloader/cropper/
audio/video/webui call the CLI has always made, uniform in shape
(handler(params, config)) so both front-ends can invoke them identically."""

from __future__ import annotations

from typing import Any, Dict, List

from rich.markup import escape

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.pipeline import load_pipeline, run_pipeline
from remanga.narration import TEMPLATE, create_narration_file
from remanga.packaging import package_chapter
from remanga.settings.project_prefs import cropper_config_for, parse_package_formats
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker
from remanga.webui import launch_and_wait_writer
from remanga.tui import confirm

# How many changed lines to show in full before summarizing the rest - enough
# to judge whether the normalizer is doing what you want, short of scrolling
# a whole chapter off the screen.
PREVIEW_LIMIT = 8


def download(params: Dict[str, Any], config: RemangaConfig) -> None:
    MangaDexDownloader(config.downloader).download_chapter(
        params.get("url"), params["chapter"], params["project"]
    )


def mark(params: Dict[str, Any], config: RemangaConfig) -> None:
    launch_panel_marker(params["project"], params["chapter"], config.marker)


def narration_init(params: Dict[str, Any], config: RemangaConfig) -> None:
    """Creates the chapter's narration.json - a full per-panel template, or a
    genuinely empty file. See remanga/narration.py for what each mode
    writes and why both exist."""
    create_narration_file(
        params["project"], params["chapter"],
        mode=params.get("mode") or TEMPLATE, force=bool(params.get("force")),
    )


def normalize_narration_cmd(params: Dict[str, Any], config: RemangaConfig) -> None:
    """Rewrites this chapter's narration.json into text that's safe to
    synthesize - see remanga/narration/normalize.py for exactly what gets
    removed and what is deliberately kept (`?`, `!` and `...` always are).

    Always previews before writing: narration text is hand-written or
    LLM-generated and can't be regenerated from anything on disk, so the
    change is shown line by line and confirmed."""
    from collections import Counter

    from remanga.narration import RULE_BY_NAME, normalize_narration, save_narration

    project, chapter = params["project"], params["chapter"]
    document, changes = normalize_narration(project, chapter)
    total = len(document.get("narration", []))

    if not changes:
        console.print(
            f"[bold green]✓ Chapter {chapter}'s narration is already TTS-safe[/] "
            f"[dim]({total} line(s) checked, nothing to change)[/]"
        )
        return

    console.print(
        f"[bold]{len(changes)} of {total} line(s) would change[/] "
        f"[dim]in chapter {chapter}'s narration.json[/]"
    )
    for change in changes[:PREVIEW_LIMIT]:
        console.print(f"\n  [bold]{escape(change.panel_id)}[/] [dim]{escape(_rule_summary(change.rules))}[/]")
        console.print(f"    [red]- {escape(change.before)}[/]")
        console.print(f"    [green]+ {escape(change.after)}[/]")
    if len(changes) > PREVIEW_LIMIT:
        console.print(f"\n  [dim]... and {len(changes) - PREVIEW_LIMIT} more line(s)[/]")

    counts = Counter(rule for change in changes for rule in change.rules)
    console.print("\n[bold]What changed, across the chapter:[/]")
    for name, count in counts.most_common():
        console.print(f"  [dim]{count:>3} line(s):[/] {RULE_BY_NAME[name].summary}")
    console.print("[dim]  ? ! and ... are never removed - only de-duplicated.[/]")

    if params.get("dry_run"):
        console.print("\n[yellow]Dry run - narration.json was not modified.[/]")
        return

    if not params.get("force") and not confirm(
        "Write these changes to narration.json?", default=True,
        note="the original text is replaced; re-running afterward changes nothing further",
    ):
        console.print("[dim]Cancelled - narration.json is unchanged.[/]")
        return

    save_narration(project, chapter, document)
    console.print(f"[bold green]✓ narration.json normalized[/] [dim]({len(changes)} line(s) rewritten)[/]")


def _rule_summary(rules: List[str]) -> str:
    from remanga.narration import RULE_BY_NAME

    return ", ".join(RULE_BY_NAME[name].summary for name in rules)


def write(params: Dict[str, Any], config: RemangaConfig) -> None:
    launch_and_wait_writer(params["project"], params["chapter"], config.writer, config.ocr)


def review(params: Dict[str, Any], config: RemangaConfig) -> None:
    # Deferred import: the wizard imports the command registry, so a
    # top-level import of it here would be circular.
    from remanga.wizard import run_narration_review_loop

    run_narration_review_loop(params["project"], params["chapter"], config)


def crop(params: Dict[str, Any], config: RemangaConfig) -> None:
    """Cuts the panels, and only that - packaging is `package`'s job."""
    from remanga.settings import package_summary

    project, chapter = params["project"], params["chapter"]
    CoordinateCropper(cropper_config_for(config, project)).crop_chapter_from_json(
        project, chapter, force=bool(params.get("force"))
    )
    formats = package_summary(cropper_config_for(config, project).package)
    if formats != "panels only":
        console.print(f"[dim]Run `package` to build the upload formats ({formats}).[/]")


def package(params: Dict[str, Any], config: RemangaConfig) -> None:
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


def tts(params: Dict[str, Any], config: RemangaConfig) -> None:
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
