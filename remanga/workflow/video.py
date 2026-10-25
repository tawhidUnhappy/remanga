"""From a pasted narration to a finished video, in four steps that each reuse
what is already done and still current. The menus run them one by one to show
each; make_video runs them in a row."""

from __future__ import annotations

import time
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.narration import load_narration, panel_files
from remanga.workflow.upload import stamp_quietly

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


def _narrated_timing(project: str, chapter: str) -> dict | None:
    """The narrated clips' timing.json, or None when the chapter was never narrated."""
    from remanga.json_io import read_json_or
    from remanga.paths import get_audio_timing_path

    timing = read_json_or(get_audio_timing_path(project, chapter, create=False), None)
    return timing if timing and timing.get("panels") else None


def narration_changed(timing: dict, panels: list) -> str | None:
    """The first panel whose narration.json text is not what was narrated, or
    None when the clips still say exactly what narration.json says."""
    wanted = [(p.panel_id, p.text) for p in panels]
    recorded = [(row.get("panel_id"), row.get("text")) for row in timing["panels"]]
    if wanted == recorded:
        return None
    return next((w[0] for w, r in zip(wanted, recorded, strict=False) if w != r), None) or "the panel list"


def check_chapter(project: str, chapter: str, config: RemangaConfig) -> dict:
    """Make video's narration check with nothing made or deleted, so many
    chapters can be checked at once (user request, 2026-10-14): narration.json
    against the cut panels, the voice rules, and whether the narration audio
    still says what narration.json says. Never raises for what it finds -
    `state` is "ok", "problems" or "not ready", with the lines that say why.
    A failing chapter gets its fix request written, as Make video does, and
    `narration` / `fix` are the narration.json to fix and that request."""
    from remanga.json_io import has_real_json_content
    from remanga.narration import FIX_REQUEST_NAME, NarrationError, page_files
    from remanga.paths import get_narration_path, get_pdf_dir

    if not page_files(project, chapter):
        return {"state": "not ready", "errors": [], "warnings": [], "notes": ["not downloaded"]}
    if not has_real_json_content(get_narration_path(project, chapter)):
        return {"state": "not ready", "errors": [], "warnings": [], "notes": ["no narration.json yet"]}
    if not panel_files(project, chapter):
        return {"state": "not ready", "errors": [], "warnings": [], "notes": ["no cut panels yet - Make PDF"]}
    try:
        panels, warnings = check_narration(project, chapter)
    except NarrationError as error:
        lines = str(error).splitlines()
        errors = [line.strip()[2:] for line in lines if line.startswith("  - ")] or lines
        fix = get_pdf_dir(project, chapter) / FIX_REQUEST_NAME
        return {"state": "problems", "errors": errors, "warnings": [], "notes": [],
                "narration": get_narration_path(project, chapter), "fix": fix if fix.exists() else None}
    warnings = warnings + quality_warnings(project, chapter, config, panels)
    timing = _narrated_timing(project, chapter)
    changed = narration_changed(timing, panels) if timing else None
    errors = [f"narration.json has changed since it was narrated (first difference: {changed}) - the audio "
              f"does not match it; Make video narrates it again"] if changed else []
    notes = [f"{len(panels)} panel(s) to narrate" + ("" if timing else ", not narrated yet")]
    return {"state": "problems" if errors else "ok", "errors": errors, "warnings": warnings, "notes": notes,
            "narration": get_narration_path(project, chapter) if errors else None, "fix": None}


def narrate(project: str, chapter: str, panels: list, config: RemangaConfig, force: bool = False,
            fresh: str | None = None) -> Path:
    """The chapter's narration - every take made before put back from the
    store, only the rest synthesized (store/versions.py:TakeCache). What the
    chapter's folders held is kept as a version first (store/versions.py:
    adopt), so nothing made before is replaced unrecorded."""
    from remanga.audio import TTSEngine
    from remanga.store import chapter_lock
    from remanga.store.versions import adopt

    with chapter_lock(project, chapter):
        _keep_what_is_there(project, chapter, config, adopt)
        return TTSEngine(config.tts, config.audio, config.subtitles).generate_narration_audio(
            project, chapter, panels, force=force or bool(fresh), fresh=fresh)


def _keep_what_is_there(project: str, chapter: str, config: RemangaConfig, adopt) -> None:
    number = adopt(project, chapter, config)
    if number:
        console.print(f"[cyan]Chapter {chapter}: what was there is kept as version {number}[/] "
                      f"[dim](the Versions menu has it)[/]")


def mix(project: str, chapter: str, config: RemangaConfig, force: bool = False) -> Path:
    from remanga.audio import mix_master_audio
    from remanga.store import chapter_lock

    with chapter_lock(project, chapter):
        return mix_master_audio(project, chapter, config.audio, force=force)


def render(project: str, chapter: str, config: RemangaConfig, force: bool = False, picture: bool = False,
           fresh: str | None = None) -> Path:
    """The chapter's video - put back from the store when one with exactly
    these inputs was made before (store/versions.py:video_key), rendered
    otherwise - then kept, and recorded as the chapter's current version.
    `picture`: the chapter's picture (video/_work/picture.mp4) must be there
    and current too, as a long video's join needs - then the renderer runs,
    remaking only what is stale. `fresh`: a run made fresh on purpose -
    rendered from scratch, kept as its own video beside any made before."""
    from remanga.paths import get_final_video_path
    from remanga.store import Store, chapter_lock
    from remanga.store.objects import recipe_key
    from remanga.store.versions import describe, record, video_recipe
    from remanga.video import VideoRenderer

    with chapter_lock(project, chapter):
        store = Store(project)
        recipe = video_recipe(project, chapter, config)
        if fresh:
            recipe["fresh"] = fresh
            force = True
        key = recipe_key("video", recipe)
        video = get_final_video_path(project, chapter)
        if not force and not picture and store.place("video", key, "recap.mp4", video):
            console.print(f"[bold green]✓ This video was made before with exactly these settings - back from "
                          f"the store, not rendered again:[/] {_esc(str(video))}")
        else:
            video = VideoRenderer(config.system, config.video).render_video(project, chapter, force=force)
            store.put("video", key, {"recap.mp4": video}, recipe, describe(config, project, chapter)[1])
            # The chapter's video is the store's file (when this key was kept
            # before, the copy just rendered gives way to it).
            store.place("video", key, "recap.mp4", video)
        number = record(project, chapter, config, key, fresh=fresh)
        console.print(f"[dim]Chapter {chapter}: version {number} is current (the Versions menu lists them all)[/]")
        return video


def remix_video(project: str, chapter: str, config: RemangaConfig) -> Path:
    """A new video from the narration clips already on disk - for when only the
    music, the sound or the video settings changed (user request, 2026-09-24).
    Nothing is deleted and nothing is narrated: the mix is redone, and the
    render re-encodes the sound and rebuilds the picture only if its own
    settings changed.

    Refuses when narration.json no longer says what the clips say - a video
    whose words and pictures disagree is worse than waiting for Make video."""
    from remanga.audio.narration_voice import voice_changed_from
    from remanga.audio.take_audio import narration_identity

    timing = _narrated_timing(project, chapter)
    if not timing:
        raise FileNotFoundError(f"Chapter {chapter} has not been narrated yet - use Make video first.")
    panels, _ = check_narration(project, chapter)
    changed = narration_changed(timing, panels)
    if changed:
        raise ValueError(f"Chapter {chapter}'s narration.json has changed since it was narrated (first "
                         f"difference: {changed}) - use Make video to narrate it again.")
    console.print(f"[bold]Chapter {chapter}:[/] reusing the {len(panels)} narrated panel(s) - no narrating")
    other_voice = voice_changed_from(timing, narration_identity(config.tts, config.audio))
    if other_voice:
        console.print(f"  [yellow]- the clips are in {_esc(other_voice)}, not the voice set now - they are "
                      f"kept as they are; Make video narrates in the new one[/]")
    from remanga.store import chapter_lock

    with chapter_lock(project, chapter):
        mix(project, chapter, config, force=True)
        video = render(project, chapter, config)
    stamp_quietly(project, chapter, video)
    return video


def remake_from_source(project: str, chapter: str, config: RemangaConfig) -> Path:
    """The whole video again from the chapter's sources alone - pages, panel
    marks and narration.json: every derived file deleted first, the panels
    cut again, then narrated, mixed and rendered (intro included)."""
    from remanga.store import chapter_lock
    from remanga.store.versions import adopt
    from remanga.workflow.cleanup import drop_derived
    from remanga.workflow.panels import cut_panels

    with chapter_lock(project, chapter):
        _keep_what_is_there(project, chapter, config, adopt)
        for path in drop_derived(project, chapter):
            console.print(f"[dim]deleted {_esc(str(path))}[/]")
        cut_panels(project, chapter, config, force=True)
        return make_video(project, chapter, config)


def make_video(project: str, chapter: str, config: RemangaConfig, force: bool = False,
              audio_only: bool = False, fresh: bool = False) -> Path:
    """The chapter's video from its narration.json. `fresh`: made all again
    from scratch - nothing reused from the store - and kept as a new version
    beside the others (user request, 2026-10-25: a choice "to generate fresh
    new ones ... for trust issues people"); at the end it says how its takes
    compare, byte for byte, with the ones made before."""
    # Everything a previous run made goes first, forced or not (user request,
    # 2026-09-21): a run means the same thing every time, and what is on disk
    # afterwards is what this run produced rather than a layer over whatever
    # was there. The PDF and everything under chapters/ are untouched - see
    # cleanup.REMADE_KINDS.
    # The chapter's folders are only a view of the store (store/versions.py):
    # clearing them loses nothing - what they held is kept as a version first,
    # and every take and video already made comes back from the store instead
    # of being made again.
    from remanga.store import chapter_lock
    from remanga.store.versions import adopt
    from remanga.workflow.cleanup import drop_audio_and_video

    panels, warnings = check_narration(project, chapter)
    with chapter_lock(project, chapter):
        _keep_what_is_there(project, chapter, config, adopt)
        drop_audio_and_video(project, chapter)
        console.print(f"Narration checked - {len(panels)} panel(s) to narrate")
        for warning in warnings + quality_warnings(project, chapter, config, panels):
            console.print(f"  [yellow]- {_esc(warning)}[/]")
        run = time.strftime("%Y%m%d-%H%M%S") if fresh else None
        if fresh:
            console.print("[bold cyan]Making it all fresh - nothing reused from the store; kept as a new "
                          "version beside the others[/]")
        narrate(project, chapter, panels, config, force, fresh=run)
        mix(project, chapter, config, force or fresh)
        video = render(project, chapter, config, force, fresh=run)
        if fresh:
            from remanga.store.versions import compare_fresh

            console.print(f"[bold green]{_esc(compare_fresh(project, chapter, config).line())}[/]")
        if audio_only:
            # Mixed and rendered anyway - it is how the narration is proven
            # good end to end - but only the raw clips are worth keeping in
            # the chapter's folders: the video is kept in the store as a
            # version, and the mix comes back from the clips when needed.
            from remanga.paths import get_audio_dir
            from remanga.workflow.cleanup import drop_mix_and_video

            drop_mix_and_video(project, chapter)
            return get_audio_dir(project, chapter, create=False)
    stamp_quietly(project, chapter, video)
    return video
