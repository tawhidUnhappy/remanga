"""Whole-manga compilation: runs every chapter's remaining pipeline steps (TTS,
frame compositing) in order, then joins them into ONE continuous recap video
instead of 24 separate ones - a single `remanga full-recap` run.

Why this isn't just "render each chapter, then ffmpeg-concat the finished
MP4s": that approach bakes background music into each chapter's audio
independently (remanga/audio/mix.py) - each chapter gets its own BGM loop
restarted from ms 0, its own fade-in/fade-out, its own separate EBU R128
loudnorm pass. Concatenating those finished files back together would give
exactly the artifacts this mode exists to avoid: BGM visibly/audibly
restarting and re-fading at every chapter boundary, and a small loudness
jump at every join since each chapter was normalized on its own.

Instead this builds one continuous timeline across the whole manga before
anything gets mixed: one combined narration track (concatenating the same
per-panel clips remanga/audio/mix.py uses - already edge-faded, see
remanga/audio/tts.py - so a chapter boundary is just another panel-to-panel
join, no different from one already handled safely inside a single chapter
today), ONE background-music loop laid under the entire thing with exactly
one fade-in at the very start and one fade-out at the very end, and exactly
one loudnorm pass over the result. Frames are concatenated the same way -
one ffmpeg concat list spanning every chapter in order, so there's no seam
where the video-side timing could drift from the audio-side timing either.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

from pydub import AudioSegment

from remanga import setup
from remanga.audio.tts import TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json
from remanga.paths import get_chapter_dir, get_project_dir, get_project_video_dir
from remanga.video.compose import FrameCompositor
from remanga.video.render import VideoRenderer


def chapter_sort_key(chapter_num: str):
    """Numeric sort where possible ("2" before "10"), falling back to plain
    string sort for anything that isn't a plain number (a bonus/special
    chapter label) - same tolerance remanga.cropper.naming.fmt_chapter has
    for non-numeric chapter labels, just for ordering instead of padding."""
    try:
        return (0, float(chapter_num))
    except ValueError:
        return (1, chapter_num)


def discover_chapters(project_name: str) -> List[str]:
    """Every chapter this project has a chapters/chapter_N/ directory for,
    in reading order. Doesn't filter by production status - callers decide
    what "ready" means for their own purpose."""
    chapters_root = get_project_dir(project_name) / "chapters"
    if not chapters_root.exists():
        return []
    nums = []
    for d in chapters_root.iterdir():
        if d.is_dir() and d.name.startswith("chapter_"):
            nums.append(d.name[len("chapter_"):])
    return sorted(nums, key=chapter_sort_key)


class FullRecapCompiler:
    """Owns one whole-manga compilation run. Reuses TTSEngine/FrameCompositor
    for the per-chapter prep work (both already resumable on their own -
    an interrupted run just picks up where it left off), then does its own
    cross-chapter audio/frame assembly and a single ffmpeg encode."""

    def __init__(self, config: Optional[RemangaConfig] = None):
        self.config = config or RemangaConfig.load()
        self._tts = TTSEngine(self.config.tts, self.config.audio)
        self._compositor = FrameCompositor(self.config.video)
        self._renderer = VideoRenderer(self.config.system, self.config.video)

    def _ensure_chapter_ready(self, project_name: str, chapter_num: str) -> Path:
        """Makes sure chapter_num has cropped panels, a narration script, its
        per-panel voice clips, and its composited frames - raising a clear,
        chapter-named error the moment any prerequisite this mode can't
        supply on its own (marking panels, writing narration) is missing,
        rather than silently skipping that chapter or failing deep inside a
        later step with no indication which chapter caused it. Returns the
        chapter's audio_timing.json path once everything's confirmed ready."""
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        panels_dir = chapter_dir / "panels"
        narration_path = chapter_dir / "narration.json"

        if not panels_dir.exists() or not any(p.is_file() for p in panels_dir.iterdir()):
            raise FileNotFoundError(
                f"Chapter {chapter_num} has no cropped panels yet - run `remanga crop` "
                f"(after marking it with `remanga mark`) for this chapter first."
            )
        if not narration_path.exists():
            raise FileNotFoundError(
                f"Chapter {chapter_num} has no narration.json yet - write/generate its "
                f"narration script first, then re-run full-recap."
            )

        self._tts.generate_narration_audio(project_name, chapter_num, interactive=False, force=False)
        self._compositor.prepare_composited_frames(project_name, chapter_num, force=False)

        timing_path = chapter_dir / "audio_timing.json"
        if not timing_path.exists():
            raise RuntimeError(f"Chapter {chapter_num}: audio_timing.json still missing after TTS - cannot continue.")
        return timing_path

    def _assemble_combined_audio(self, project_name: str, chapters: List[str], timing_paths: List[Path]) -> Tuple[Path, List[Tuple[Path, float]]]:
        """Builds ONE narration track spanning every chapter (concatenating
        the same already edge-faded per-panel clips remanga/audio/mix.py
        uses within a single chapter - see module docstring), overlays ONE
        continuous background-music loop under the whole thing, and applies
        ONE loudnorm pass - never per chapter. Returns the finished master
        WAV path plus the (frame_path, duration_sec) timeline every frame in
        the whole manga plays for, in order, for the video side to reuse
        without re-deriving it."""
        audio_config = self.config.audio
        full_config = self.config

        valid_bgm = setup.ensure_valid_bgm(full_config, interactive=False)

        combined_voice = AudioSegment.empty()
        frame_timeline: List[Tuple[Path, float]] = []

        console.print("[cyan]Assembling one continuous narration track across every chapter...[/]")
        for chapter_num, timing_path in zip(chapters, timing_paths):
            chapter_dir = get_chapter_dir(project_name, chapter_num)
            audio_dir = chapter_dir / "audio"
            frames_dir = chapter_dir / "video" / "frames"
            timing = read_json(timing_path)

            for p in timing.get("panels", []):
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

        video_dir = get_project_video_dir(project_name)
        raw_path = video_dir / f"{project_name}_full_master_raw.wav"
        final_path = video_dir / f"{project_name}_full_master.wav"
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
                run_ffmpeg(cmd, check=True, capture=True)
                raw_path.unlink(missing_ok=True)
            except Exception as e:
                console.print(f"[yellow]Loudnorm filter warning: {e}. Falling back to the un-normalized full-manga track.[/]")
                raw_path.rename(final_path)
        else:
            raw_path.rename(final_path)

        return final_path, frame_timeline

    def compile_full_manga(self, project_name: str, force: bool = False, chapters: Optional[List[str]] = None) -> Path:
        video_dir = get_project_video_dir(project_name)
        final_video = video_dir / f"{project_name}_full_recap.mp4"

        if not force and final_video.exists() and final_video.stat().st_size > 1000:
            console.print(f"[bold green]✓ Full-manga recap already compiled:[/] {_esc(str(final_video))}")
            return final_video

        chapter_list = chapters or discover_chapters(project_name)
        if not chapter_list:
            raise FileNotFoundError(f"No chapters found for project '{project_name}'.")

        start_time = time.perf_counter()
        console.print(f"[bold cyan]Compiling {len(chapter_list)} chapter(s) into one continuous recap:[/] {', '.join(chapter_list)}")

        timing_paths = []
        for i, chapter_num in enumerate(chapter_list, start=1):
            console.print(f"[cyan]({i}/{len(chapter_list)}) Preparing chapter {chapter_num}...[/]")
            timing_paths.append(self._ensure_chapter_ready(project_name, chapter_num))

        master_audio_path, frame_timeline = self._assemble_combined_audio(project_name, chapter_list, timing_paths)
        if not frame_timeline:
            raise RuntimeError("No panels found across any chapter - nothing to compile.")

        # One concat list spanning every frame of every chapter, in order -
        # identical mechanism to VideoRenderer.render_video's per-chapter
        # concat list (see remanga/video/render.py), just never restarted at
        # a chapter boundary, so there's no seam for video/audio timing to
        # drift apart at.
        concat_file = video_dir / f"{project_name}_full_concat_list.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for frame_path, duration in frame_timeline:
                f.write(f"file '{frame_path.resolve()}'\n")
                f.write(f"duration {duration}\n")
            last_frame = frame_timeline[-1][0]
            f.write(f"file '{last_frame.resolve()}'\n")

        gpu_ffmpeg, note = self._renderer._resolve_gpu_ffmpeg()
        use_gpu = gpu_ffmpeg is not None
        codec = self.config.system.gpu_codec if use_gpu else self.config.system.fallback_codec
        ffmpeg_bin = gpu_ffmpeg or "ffmpeg"
        console.print(f"[cyan]Rendering full-manga video using codec:[/] [bold]{codec}[/] [dim]({'Hardware GPU' if use_gpu else 'CPU fallback'})[/]")
        if note:
            console.print(f"[dim]({note})[/]")

        cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-i", str(master_audio_path),
            "-vf", f"fps={self.config.video.fps},format=yuv420p",
            "-c:v", codec,
        ]
        if not use_gpu:
            cmd.extend(["-preset", "medium", "-crf", "19", "-threads", str(self.config.system.threads)])
        else:
            cmd.extend(["-preset", "p6", "-cq", "20"])
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest", str(final_video)])

        console.print("[yellow]Encoding the full-manga recap... This may take a while for a long manga.[/]")
        result = run_ffmpeg(cmd, capture=True)
        if result.returncode != 0:
            console.print(f"[red]FFmpeg Error Details:\n{result.stderr}[/]")
            raise RuntimeError("FFmpeg full-manga rendering failed.")

        total_video_sec = sum(d for _, d in frame_timeline)
        elapsed_sec = time.perf_counter() - start_time
        console.print(f"[bold green]✓ Full-manga recap compiled successfully![/] "
                       f"[dim]({len(chapter_list)} chapters, {_fmt_duration(total_video_sec)} runtime, "
                       f"{_fmt_duration(elapsed_sec)} to compile)[/]")
        console.print(f"[bold green]Location:[/] {_esc(str(final_video))}")
        return final_video


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"
