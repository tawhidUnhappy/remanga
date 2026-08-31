"""Whole-manga compilation: runs every chapter's remaining pipeline steps (TTS,
mix, render) in order - producing and KEEPING each chapter's own final MP4,
exactly like running `remanga render` on it one at a time would - then joins
all of them into ONE continuous recap video instead of leaving 24 separate
ones as the only whole-manga option.

Why the join isn't just "ffmpeg-concat the per-chapter MP4s just built":
each chapter's audio/mix.py bakes background music into that chapter's own
audio independently - its own BGM loop restarted from ms 0, its own
fade-in/fade-out, its own separate EBU R128 loudnorm pass. Concatenating
those finished files back together would give exactly the artifacts this
mode exists to avoid: BGM visibly/audibly restarting and re-fading at every
chapter boundary, and a small loudness jump at every join since each
chapter was normalized on its own.

Instead the join step builds one continuous timeline across the whole manga
from scratch: one combined narration track (concatenating the same
per-panel voice clips remanga/audio/mix.py uses - already edge-faded, see
remanga/audio/tts.py - so a chapter boundary is just another panel-to-panel
join, no different from one already handled safely inside a single chapter
today), ONE background-music loop laid under the entire thing with exactly
one fade-in at the very start and one fade-out at the very end, and exactly
one loudnorm pass over the result. Frames are concatenated the same way -
one ffmpeg concat list spanning every chapter in order, so there's no seam
where the video-side timing could drift from the audio-side timing either.

Keeping each chapter's own MP4 (rather than treating it as a throwaway
intermediate) is deliberate: TTS and frame compositing are the genuinely
expensive steps here and are already cached/resumable, but so is the mix
(audio/mix.py) and per-chapter render (video/render.py) now - re-running
`full-recap` after only changing config.json's BGM path/volume re-mixes and
re-encodes just the per-chapter video (video/render.py auto-detects a newer
master_audio.wav and re-encodes even without --force), never touching TTS
or frame compositing. The whole-manga join itself still needs an explicit
--force to rebuild, since detecting "did anything downstream change" across
every chapter at once isn't worth the complexity for an occasional
whole-manga operation.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

from pydub import AudioSegment

from remanga import setup
from remanga.audio.mix import AudioProcessor
from remanga.audio.tts import TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json
from remanga.paths import (
    get_audio_dir, get_audio_timing_path, get_chapter_dir, get_final_video_path,
    get_full_recap_concat_path, get_full_recap_master_audio_path, get_full_recap_video_path,
    get_project_dir, get_video_frames_dir,
)
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
    """Owns one whole-manga compilation run. Reuses TTSEngine/AudioProcessor/
    VideoRenderer for the per-chapter work (all already resumable on their
    own - an interrupted run just picks up where it left off), then does its
    own cross-chapter audio/frame assembly and a single ffmpeg encode for
    the join."""

    def __init__(self, config: Optional[RemangaConfig] = None):
        self.config = config or RemangaConfig.load()
        self._tts = TTSEngine(self.config.tts, self.config.audio)
        self._mixer = AudioProcessor(self.config.audio)
        self._compositor = FrameCompositor(self.config.video)
        self._renderer = VideoRenderer(self.config.system, self.config.video)

    def _ensure_chapter_video(self, project_name: str, chapter_num: str, force: bool) -> Path:
        """Makes sure chapter_num has cropped panels, a narration script,
        its per-panel voice clips, its mixed master audio, and its own
        final rendered MP4 - raising a clear, chapter-named error the
        moment any prerequisite this mode can't supply on its own (marking
        panels, writing narration) is missing, rather than silently
        skipping that chapter or failing deep inside a later step with no
        indication which chapter caused it. Returns the chapter's own
        final video path once it's confirmed ready."""
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
        self._mixer.mix_master_audio(project_name, chapter_num, interactive=False)
        return self._renderer.render_video(project_name, chapter_num, force=force)

    def _assemble_combined_audio(self, project_name: str, chapters: List[str]) -> Tuple[Path, List[Tuple[Path, float]]]:
        """Builds ONE narration track spanning every chapter (concatenating
        the same already edge-faded per-panel clips remanga/audio/mix.py
        uses within a single chapter - see module docstring), overlays ONE
        continuous background-music loop under the whole thing, and applies
        ONE loudnorm pass - never per chapter. Returns the finished master
        WAV path plus the (frame_path, duration_sec) timeline every frame in
        the whole manga plays for, in order, for the video side to reuse
        without re-deriving it."""
        audio_config = self.config.audio
        valid_bgm = setup.ensure_valid_bgm(self.config, interactive=False)

        combined_voice = AudioSegment.empty()
        frame_timeline: List[Tuple[Path, float]] = []

        console.print("[cyan]Assembling one continuous narration track across every chapter...[/]")
        for chapter_num in chapters:
            audio_dir = get_audio_dir(project_name, chapter_num)
            frames_dir = get_video_frames_dir(project_name, chapter_num)
            timing = read_json(get_audio_timing_path(project_name, chapter_num))

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
                run_ffmpeg(cmd, check=True, capture=True)
                raw_path.unlink(missing_ok=True)
            except Exception as e:
                console.print(f"[yellow]Loudnorm filter warning: {_esc(str(e))}. Falling back to the un-normalized full-manga track.[/]")
                raw_path.rename(final_path)
        else:
            raw_path.rename(final_path)

        return final_path, frame_timeline

    def compile_full_manga(self, project_name: str, force: bool = False, chapters: Optional[List[str]] = None) -> Path:
        final_video = get_full_recap_video_path(project_name)

        if not force and final_video.exists() and final_video.stat().st_size > 1000:
            console.print(f"[bold green]✓ Full-manga recap already compiled:[/] {_esc(str(final_video))}")
            return final_video

        chapter_list = chapters or discover_chapters(project_name)
        if not chapter_list:
            raise FileNotFoundError(f"No chapters found for project '{project_name}'.")

        start_time = time.perf_counter()
        console.print(f"[bold cyan]Compiling {len(chapter_list)} chapter(s) into one continuous recap:[/] {', '.join(chapter_list)}")

        # Phase 1: every chapter's OWN final video first (kept, not a
        # throwaway) - each one independently resumable/cheap-to-rebuild via
        # TTSEngine/AudioProcessor/VideoRenderer's own caching.
        chapter_videos: List[Path] = []
        for i, chapter_num in enumerate(chapter_list, start=1):
            console.print(f"[cyan]({i}/{len(chapter_list)}) Preparing chapter {chapter_num}...[/]")
            chapter_videos.append(self._ensure_chapter_video(project_name, chapter_num, force=force))

        # Phase 2: the whole-manga join - a fresh continuous audio timeline
        # (see _assemble_combined_audio's docstring for why this can't just
        # reuse the per-chapter mixed audio from phase 1) plus one concat
        # list spanning every chapter's frames in order.
        master_audio_path, frame_timeline = self._assemble_combined_audio(project_name, chapter_list)
        if not frame_timeline:
            raise RuntimeError("No panels found across any chapter - nothing to compile.")

        concat_file = get_full_recap_concat_path(project_name)
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
            console.print(f"[red]FFmpeg Error Details:\n{_esc(result.stderr)}[/]")
            raise RuntimeError("FFmpeg full-manga rendering failed.")

        total_video_sec = sum(d for _, d in frame_timeline)
        elapsed_sec = time.perf_counter() - start_time
        console.print(f"[bold green]✓ Full-manga recap compiled successfully![/] "
                       f"[dim]({len(chapter_list)} chapters, {_fmt_duration(total_video_sec)} runtime, "
                       f"{_fmt_duration(elapsed_sec)} to compile)[/]")
        console.print(f"[bold green]Location:[/] {_esc(str(final_video))}")
        console.print(f"[dim]Per-chapter videos kept at:[/] {_esc(str(get_final_video_path(project_name, chapter_list[0]).parent.parent))}/*/")
        return final_video


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"
