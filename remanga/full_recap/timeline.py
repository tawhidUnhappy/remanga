"""Building ONE continuous audio timeline across every chapter.

This is why a full recap isn't just "ffmpeg-concat the per-chapter MP4s".
Each chapter's mix bakes in its own BGM loop from ms 0, its own fade-in and
fade-out, and its own EBU R128 loudnorm pass; concatenating those finished
files gives exactly the artifacts this mode exists to avoid - music
restarting and re-fading at every chapter boundary, and a loudness jump at
every join.

So the timeline is rebuilt from scratch instead: one narration track
concatenated from the same already-edge-faded per-panel clips a single
chapter's mix uses (which makes a chapter boundary just another
panel-to-panel join), ONE background-music loop under the whole thing with
exactly one fade-in at the start and one fade-out at the end, and exactly
one loudnorm pass over the result. The frame timeline it returns is built in
the same pass from the same per-panel timings, so the video side can't drift
from the audio side."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from pydub import AudioSegment
from rich.progress import BarColumn, Progress, TextColumn

from remanga import settings
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json
from remanga.paths import (
    get_audio_dir, get_audio_timing_path, get_full_recap_master_audio_path, get_video_frames_dir,
)


def assemble_combined_audio(
    config: RemangaConfig, project_name: str, chapters: List[str],
) -> Tuple[Path, List[Tuple[Path, float]]]:
    """Returns the finished master WAV path plus the (frame_path,
    duration_sec) timeline every frame in the whole manga plays for, in
    order, for the video side to reuse without re-deriving it."""
    audio_config = config.audio
    valid_bgm = settings.ensure_valid_bgm(config, interactive=False)

    combined_voice = AudioSegment.empty()
    frame_timeline: List[Tuple[Path, float]] = []

    # Load every chapter's panel timing up front so the progress bar below
    # can show a real total (every panel across the whole manga) instead
    # of restarting from 0 at each chapter boundary.
    per_chapter_timing = [
        (chapter_num, read_json(get_audio_timing_path(project_name, chapter_num)).get("panels", []))
        for chapter_num in chapters
    ]
    total_panels = sum(len(panels) for _, panels in per_chapter_timing)

    console.print("[cyan]Assembling one continuous narration track across every chapter...[/]")
    # This is pure CPU work (pydub decoding/concatenating every panel's WAV
    # clip in sequence, plus PIL frame compositing next) - the GPU-accelerated
    # part of this whole pipeline is only the final ffmpeg encode below,
    # which now shows its own live progress too. Silent for a couple thousand
    # panels' worth of I/O otherwise looked identical to a hang.
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} panels"),
        refresh_per_second=4,
    ) as progress:
        task = progress.add_task("[yellow]Concatenating narration clips...", total=total_panels)
        for chapter_num, panels in per_chapter_timing:
            audio_dir = get_audio_dir(project_name, chapter_num)
            frames_dir = get_video_frames_dir(project_name, chapter_num)

            for p in panels:
                clip_file = audio_dir / p["audio_file"]
                if clip_file.exists():
                    segment = AudioSegment.from_file(clip_file)
                else:
                    segment = AudioSegment.silent(duration=p["duration_ms"], frame_rate=audio_config.sample_rate)
                combined_voice += segment

                pause_ms = p.get("pause_after_ms", 0)
                if pause_ms > 0:
                    combined_voice += AudioSegment.silent(duration=pause_ms, frame_rate=audio_config.sample_rate)

                frame_timeline.append((frames_dir / f"frame_{p['panel_id']}.png", p["total_slot_sec"]))
                progress.update(task, advance=1)

    master_audio = combined_voice.set_channels(2).set_frame_rate(audio_config.sample_rate)

    if valid_bgm and audio_config.bgm_enabled:
        console.print(f"[cyan]Overlaying one continuous background music track (no per-chapter restarts):[/] {_esc(valid_bgm)}")
        bgm_track = AudioSegment.from_file(valid_bgm)
        bgm_track = bgm_track.set_channels(2).set_frame_rate(audio_config.sample_rate)
        bgm_track = bgm_track + audio_config.bgm_volume_db

        total_duration_ms = len(master_audio)
        loop_count = (total_duration_ms // max(1, len(bgm_track))) + 1
        bgm_loop = (bgm_track * loop_count)[:total_duration_ms]
        # Exactly one fade-in and one fade-out for the WHOLE manga - not
        # per chapter - so the music never visibly/audibly restarts at a
        # chapter join.
        bgm_loop = bgm_loop.fade_in(1500).fade_out(2000)

        master_audio = bgm_loop.overlay(master_audio)
    elif audio_config.bgm_enabled:
        console.print("[yellow]BGM is enabled in config, but no valid BGM file was found. Continuing without BGM.[/]")

    final_path = get_full_recap_master_audio_path(project_name)
    raw_path = final_path.with_name(final_path.stem + "_raw.wav")
    master_audio.export(raw_path, format="wav")

    if audio_config.enable_loudnorm:
        console.print("[cyan]Applying a single EBU R128 normalization pass over the full-manga track...[/]")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(raw_path),
            "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
            "-ar", str(audio_config.sample_rate),
            str(final_path),
        ]
        try:
            run_ffmpeg(cmd, check=True, capture=True, show_progress=True,
                       total_seconds=len(master_audio) / 1000.0,
                       description="Normalizing full-manga audio")
            raw_path.unlink(missing_ok=True)
        except Exception as e:
            console.print(f"[yellow]Loudnorm filter warning: {_esc(str(e))}. Falling back to the un-normalized full-manga track.[/]")
            raw_path.rename(final_path)
    else:
        raw_path.rename(final_path)

    return final_path, frame_timeline

