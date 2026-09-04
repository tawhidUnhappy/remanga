"""Remix: re-run just the audio mix + video encode for a project's
chapter(s) - the cheap steps - after a BGM/volume-only change, without
re-running TTS or frame compositing. This is what makes "keep each
chapter's own video, then join them" (see remanga/full_recap/) actually useful
day to day: change config.json's bgm_path/bgm_volume_db (or pass --bgm),
run this, and only the audio mix and the final ffmpeg encode redo - per
chapter and, if asked, for the whole-manga joined video too.

video/render.py already auto-detects a master_audio.wav newer than its last
render and re-encodes even without --force (see its docstring) - mixing
here always rewrites master_audio.wav, so simply mixing-then-rendering is
enough to get that pickup for free; the "remix" concept this module adds is
just doing that across every chapter of a project (or a chosen subset) in
one call, and optionally re-joining the whole-manga video afterward."""

from __future__ import annotations

from typing import List, Optional

from remanga.audio.mix import AudioProcessor
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.full_recap import FullRecapCompiler, chapter_sort_key, discover_chapters
from remanga.paths import get_final_video_path, get_full_recap_video_path
from remanga.video.render import VideoRenderer


def remix_project(
    project_name: str,
    config: Optional[RemangaConfig] = None,
    chapters: Optional[List[str]] = None,
    bgm_override: Optional[str] = None,
    rejoin: bool = True,
) -> None:
    """Re-mixes and re-renders every chapter in `chapters` (default: every
    chapter the project has), then - if `rejoin` and a full-recap video
    already exists for this project - recompiles the whole-manga join too,
    so the joined video never silently drifts out of sync with a BGM/volume
    change applied to its chapters. Never touches TTS or frame compositing:
    per-panel voice clips and composited frames are untouched by every step
    here."""
    config = config or RemangaConfig.load()
    chapter_list = chapters or discover_chapters(project_name)
    if not chapter_list:
        raise FileNotFoundError(f"No chapters found for project '{project_name}'.")
    chapter_list = sorted(chapter_list, key=chapter_sort_key)

    mixer = AudioProcessor(config.audio)
    renderer = VideoRenderer(config.system, config.video)

    console.print(f"[bold cyan]Remixing {len(chapter_list)} chapter(s) for '{project_name}'[/] [dim](audio mix + video re-encode only - no re-narration)[/]")
    for i, chapter_num in enumerate(chapter_list, start=1):
        console.print(f"[cyan]({i}/{len(chapter_list)}) Chapter {chapter_num}...[/]")
        # force=True: remix's whole purpose is "redo the mix" - if the user
        # re-ran remix with identical settings on purpose (e.g. suspecting a
        # bad mix), skipping it because the fingerprint looks unchanged
        # would be the wrong call here specifically.
        mixer.mix_master_audio(project_name, chapter_num, bgm_override=bgm_override, interactive=False, force=True)
        renderer.render_video(project_name, chapter_num, force=False)

    full_video = get_full_recap_video_path(project_name)
    if rejoin and full_video.exists():
        # Always re-join the FULL current chapter set (not just whatever
        # subset was remixed) - a joined video missing chapters this remix
        # didn't touch would be a worse surprise than re-joining a couple of
        # unchanged chapters too.
        console.print("[bold cyan]Re-joining the whole-manga video with the updated mix...[/]")
        # force_chapters=False: every chapter was just mixed/rendered above -
        # forcing them again here would just repeat identical ffmpeg work.
        FullRecapCompiler(config).compile_full_manga(project_name, force=True, force_chapters=False)
    elif not full_video.exists():
        console.print(f"[dim](No existing full-recap video for '{project_name}' to re-join - run `remanga full-recap` first if you want one.)[/]")

    console.print(f"[bold green]✓ Remix complete for {len(chapter_list)} chapter(s).[/]")
    for chapter_num in chapter_list:
        console.print(f"  [dim]Chapter {chapter_num}:[/] {_esc(str(get_final_video_path(project_name, chapter_num, create=False)))}")
