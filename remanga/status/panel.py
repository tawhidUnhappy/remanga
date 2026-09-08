"""The `status` command's printed report: one chapter's production state,
plus the settings that will shape it when it's rendered."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import display_path, escape as _esc, wrap_at_slashes
from remanga.paths import load_project_metadata
from remanga.settings import package_summary
from remanga.status.badges import absent, artifact, counted, done, flagged, missing, off, pending
from remanga.status.compute import get_chapter_status


def render_status_panel(project: str, chapter: str) -> str:
    """Builds the plain-text chapter production status summary for the CLI."""
    st = get_chapter_status(project, chapter)
    meta = load_project_metadata(project)
    saved_url = wrap_at_slashes(meta.get("manga_url") or meta.get("manga_id", "Not set"))

    # This project's settings, not the machine's - the panel says what a
    # render of THIS chapter would use.
    config = RemangaConfig.load().for_project(project)
    # A NAME from the engine's own catalogue, not a path on disk. This used
    # to stat() it as a file, which meant a perfectly configured voice was
    # reported as "Not set / Missing" on every single run - the engines that
    # took a reference WAV are gone, and the check went stale with them.
    voice = config.tts.kokoro.spec if config.tts.active_voice else None
    voice_status = (
        f"[green]{voice.label} ({voice.name}, grade {voice.grade})[/]"
        if voice else "[yellow]Not set[/]"
    )

    bgm_path = Path(config.audio.bgm_path).expanduser() if config.audio.bgm_path else None
    bgm_status = (
        f"[green]Enabled ({display_path(bgm_path)})[/]"
        if (config.audio.bgm_enabled and bgm_path and bgm_path.exists())
        else "[dim]Disabled / None[/]"
    )

    res_str = f"{config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)"
    package = config.cropper.package
    # Same one-line rendering the settings screen uses, so "what does this
    # chapter get packaged into" reads identically wherever it's asked.
    package_str = package_summary(package)

    # Items 2-9 below name only the filename, not the full path - the
    # workspace directory they all live under is already stated once, in
    # "Workspace Directory" above. Repeating the full absolute path on every
    # line (the old behavior) made this panel wrap mid-directory-name on
    # anything narrower than a very wide terminal; a bare filename never
    # needs to wrap at all.
    # Hoisted out of the template below rather than inlined like the
    # shorter rows: inside a triple-quoted f-string there is nowhere to wrap
    # a long expression - every newline would land in the printed report.
    review_status = (
        flagged(f"{st['review_flagged_count']} flagged, awaiting LLM fix pass")
        if st["review_pending"] else off("no pending review")
    )
    audio_status = (
        done("Generated (Kokoro-82M)") if st["master_audio_exist"]
        else missing(f"Not built ({st['audio_clips_count']}/{st['total_narration_entries']} clips)")
    )
    video_status = (
        done(f"Ready ({_esc(st['video_path'].name)})") if st["video_exist"] else missing("Not rendered")
    )

    status_str = f"""
[bold]Project:[/] {project} | [bold]Chapter:[/] {chapter}
[bold]Saved Manga Source:[/] {saved_url}
[bold]Workspace Directory:[/] {display_path(st['chap_dir'])}
[bold]Video Resolution:[/] {res_str}
[bold]Vision outputs:[/] {package_str}
[bold]Narrator Voice:[/] {voice_status}
[bold]Background Music:[/] {bgm_status}

   1. Pages Downloaded    : {counted(st['pages_count'], 'pages')}
   2. Pages ZIP Archive   : {done('Ready (pages.zip)') if st['pages_zip_exist'] else pending()}
   3. Crop Instructions   : {done('Present (crops.json)') if st['crops_exist'] else absent()}
   4. Panels Cropped      : {counted(st['panels_count'], 'panels')}
   5. Panel Contact Sheets: {counted(st['sheets_count'], 'sheets', empty=pending())}
   6. panels_zip          : {artifact(st['panels_zip_built'], package.panels_zip_active)}
   7. pdf                 : {artifact(st['panels_pdf_built'], package.pdf_active)}
   8. sheets_zip          : {artifact(st['sheets_zip_built'], package.sheets_zip_active)}
   9. Narration Script    : {done('Present (narration.json)') if st['narration_exist'] else absent()}
   9b. Narration Review   : {review_status}
  10. Master Audio Track  : {audio_status}
  11. Final Recap Video   : {video_status}
"""
    return status_str.strip()
