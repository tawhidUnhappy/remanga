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

    return TTSEngine(config.tts, config.audio, config.subtitles).generate_narration_audio(
        project, chapter, panels, force=force)


def mix(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> Path:
    from remanga.audio import mix_master_audio

    return mix_master_audio(project, chapter, config.audio, force=force)


def render(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> Path:
    from remanga.video import VideoRenderer

    return VideoRenderer(config.system, config.video).render_video(project, chapter, force=force)


def remix_video(project: str, chapter: str, config: RemangaConfig) -> Path:
    """A new video from the narration clips already on disk - for when only the
    music, the sound or the video settings changed (user request, 2026-09-24).
    Nothing is deleted and nothing is narrated: the mix is redone, and the
    render re-encodes the sound and rebuilds the picture only if its own
    settings changed.

    Refuses when narration.json no longer says what the clips say - a video
    whose words and pictures disagree is worse than waiting for Make video."""
    from remanga.audio.narration_voice import voice_changed_from
    from remanga.json_io import read_json_or
    from remanga.paths import get_audio_timing_path

    timing = read_json_or(get_audio_timing_path(project, chapter, create=False), None)
    if not timing or not timing.get("panels"):
        raise FileNotFoundError(f"Chapter {chapter} has not been narrated yet - use Make video first.")
    panels, _ = check_narration(project, chapter)
    wanted = [(p.panel_id, p.text) for p in panels]
    recorded = [(row.get("panel_id"), row.get("text")) for row in timing["panels"]]
    if wanted != recorded:
        changed = next((w[0] for w, r in zip(wanted, recorded, strict=False) if w != r), None) or "the panel list"
        raise ValueError(f"Chapter {chapter}'s narration.json has changed since it was narrated (first "
                         f"difference: {changed}) - use Make video to narrate it again.")
    console.print(f"[bold]Chapter {chapter}:[/] reusing the {len(panels)} narrated panel(s) - no narrating")
    other_voice = voice_changed_from(timing, config.tts.identity())
    if other_voice:
        console.print(f"  [yellow]- the clips are in {_esc(other_voice)}, not the voice set now - they are "
                      f"kept as they are; Make video narrates in the new one[/]")
    mix(project, chapter, config, force=True)
    return render(project, chapter, config)


def remake_from_source(project: str, chapter: str, config: RemangaConfig) -> Path:
    """The whole video again from the chapter's sources alone - pages, panel
    marks and narration.json: every derived file deleted first, the panels
    cut again, then narrated, mixed and rendered (intro included)."""
    from remanga.workflow.cleanup import drop_derived
    from remanga.workflow.panels import cut_panels

    for path in drop_derived(project, chapter):
        console.print(f"[dim]deleted {_esc(str(path))}[/]")
    cut_panels(project, chapter, config, force=True)
    return make_video(project, chapter, config)


def make_video(project: str, chapter: str, config: RemangaConfig, force: bool = False,
              audio_only: bool = False) -> Path:
    # Everything a previous run made goes first, forced or not (user request,
    # 2026-09-21): a run means the same thing every time, and what is on disk
    # afterwards is what this run produced rather than a layer over whatever
    # was there. The PDF and everything under chapters/ are untouched - see
    # cleanup.REMADE_KINDS.
    from remanga.workflow.cleanup import drop_audio_and_video

    panels, warnings = check_narration(project, chapter)
    drop_audio_and_video(project, chapter)
    console.print(f"[bold]Chapter {chapter}:[/] narration checked - {len(panels)} panel(s) to narrate")
    for warning in warnings + quality_warnings(project, chapter, config, panels):
        console.print(f"  [yellow]- {_esc(warning)}[/]")
    narrate(project, chapter, panels, config, force)
    mix(project, chapter, config, force)
    video = render(project, chapter, config, force)
    if audio_only:
        # Mixed and rendered anyway - it is how the narration is proven good
        # end to end - but only the raw clips are worth keeping: the mix and
        # the render come back later from them (make_video, unforced) rather
        # than sitting on disk twice.
        from remanga.paths import get_audio_dir
        from remanga.workflow.cleanup import drop_mix_and_video

        drop_mix_and_video(project, chapter)
        return get_audio_dir(project, chapter, create=False)
    return video
