"""From a pasted narration to a finished video, in four steps that each reuse
what is already done and still current. The menus run them one by one to show
each; make_video runs them in a row."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.narration import load_narration, panel_files

# Four steps, each reusing what is already done and still current. The menus
# run them one by one to show each; make_video runs them in a row.


def check_narration(project: str, chapter: str) -> tuple[list, list[str]]:
    """The panels to narrate and the check's warnings; raises NarrationError
    (after writing the fix request) when it doesn't check out."""
    panels, check = load_narration(project, chapter)
    return panels, check.warnings


def quality_warnings(project: str, chapter: str, config: RemangaConfig, panels: list | None = None) -> list[str]:
    """Panels this video size would show smaller than they are - detail lost
    for nothing, since the panels themselves are full resolution. `panels` is
    the narrated ones (StoryPanel) when they are known, so a skipped panel is
    not counted for a video it never appears in."""
    from remanga.video.compose import quality_warning

    shown = [getattr(p, "panel", p) for p in panels] if panels is not None else panel_files(project, chapter)
    warning = quality_warning(shown, config.video)
    return [warning] if warning else []


def narrate(project: str, chapter: str, panels: list, config: RemangaConfig, force: bool = False) -> Path:
    from remanga.audio import TTSEngine

    return TTSEngine(config.tts, config.audio).generate_narration_audio(project, chapter, panels, force=force)


def mix(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> Path:
    from remanga.audio import mix_master_audio

    return mix_master_audio(project, chapter, config.audio, force=force)


def render(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> Path:
    from remanga.video import VideoRenderer

    return VideoRenderer(config.system, config.video).render_video(project, chapter, force=force)


def make_video(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> Path:
    panels, warnings = check_narration(project, chapter)
    console.print(f"[bold]Chapter {chapter}:[/] narration checked - {len(panels)} panel(s) to narrate")
    for warning in warnings + quality_warnings(project, chapter, config, panels):
        console.print(f"  [yellow]- {_esc(warning)}[/]")
    narrate(project, chapter, panels, config, force)
    mix(project, chapter, config, force)
    return render(project, chapter, config, force)
