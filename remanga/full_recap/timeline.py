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
one loudnorm pass over the result. Each chapter's stretch is padded out to
the length of that chapter's picture stream, which the join stream-copies
alongside it, so the video side can't drift from the audio side."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from rich.progress import BarColumn, Progress, TextColumn

from remanga import settings
from remanga.audio.join import join_segments
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json
from remanga.paths import get_audio_dir, get_audio_timing_path, get_full_recap_master_audio_path


def assemble_combined_audio(
    config: RemangaConfig, project_name: str, chapters: list[str],
    chapter_lengths_sec: list[float] | None = None,
) -> Path:
    """Returns the finished master WAV path.

    `chapter_lengths_sec` (one per chapter) pads each chapter's narration
    with silence out to that running length: the whole-frame length of the
    chapter's picture, which ends up to one frame after its last word.
    Unpadded, every chapter boundary would put the sound that much ahead of
    the picture, and over dozens of chapters those add up."""
    if chapter_lengths_sec is not None and len(chapter_lengths_sec) != len(chapters):
        raise ValueError(f"{len(chapter_lengths_sec)} chapter lengths given for {len(chapters)} chapters")
    audio_config = config.audio
    sample_rate = audio_config.sample_rate
    valid_bgm = settings.ensure_valid_bgm(config, interactive=False)

    # Load every chapter's panel timing up front so the progress bar below
    # can show a real total (every panel across the whole manga) instead
    # of restarting from 0 at each chapter boundary.
    per_chapter_timing = [
        (chapter_num, read_json(get_audio_timing_path(project_name, chapter_num)).get("panels", []))
        for chapter_num in chapters
    ]
    total_panels = sum(len(panels) for _, panels in per_chapter_timing)

    segments: list[AudioSegment] = []
    samples = 0  # running length at sample_rate, exact - pydub's len() rounds to whole ms per segment
    boundary_sec = 0.0

    def add(segment: AudioSegment) -> None:
        nonlocal samples
        segments.append(segment)
        samples += round(segment.frame_count() * sample_rate / segment.frame_rate)

    console.print("[cyan]Assembling one continuous narration track across every chapter...[/]")
    # Pure CPU work (pydub decoding every panel's WAV clip in sequence), and
    # without a bar a couple thousand panels' worth of it looks exactly like
    # a hang.
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} panels"),
        refresh_per_second=4,
    ) as progress:
        task = progress.add_task("[yellow]Concatenating narration clips...", total=total_panels)
        for index, (chapter_num, panels) in enumerate(per_chapter_timing):
            audio_dir = get_audio_dir(project_name, chapter_num)

            for p in panels:
                clip_file = audio_dir / p["audio_file"]
                if clip_file.exists():
                    add(AudioSegment.from_file(clip_file))
                else:
                    add(AudioSegment.silent(duration=p["duration_ms"], frame_rate=sample_rate))

                pause_ms = p.get("pause_after_ms", 0)
                if pause_ms > 0:
                    add(AudioSegment.silent(duration=pause_ms, frame_rate=sample_rate))
                progress.update(task, advance=1)

            if chapter_lengths_sec is not None:
                boundary_sec += chapter_lengths_sec[index]
                gap = round(boundary_sec * sample_rate) - samples
                if gap > 0:
                    add(AudioSegment.silent(duration=gap * 1000 / sample_rate, frame_rate=sample_rate))

    # One join rather than `+=` per clip - 168.9s -> 0.23s on an 82-minute
    # recap, see audio/join.py.
    master_audio = join_segments(segments).set_channels(2).set_frame_rate(sample_rate)

    if valid_bgm and audio_config.bgm_enabled:
        console.print(
            f"[cyan]Overlaying one continuous background music track (no per-chapter restarts):[/] {_esc(valid_bgm)}"
        )
        bgm_track = AudioSegment.from_file(valid_bgm)
        bgm_track = bgm_track.set_channels(2).set_frame_rate(sample_rate)
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
            "-ar", str(sample_rate),
            str(final_path),
        ]
        try:
            run_ffmpeg(cmd, check=True, capture=True, show_progress=True,
                       total_seconds=len(master_audio) / 1000.0,
                       description="Normalizing full-manga audio")
            raw_path.unlink(missing_ok=True)
        except Exception as e:
            console.print(
                f"[yellow]Loudnorm filter warning: {_esc(str(e))}. Falling back to the un-normalized full-manga "
                f"track.[/]"
            )
            raw_path.rename(final_path)
    else:
        raw_path.rename(final_path)

    return final_path
