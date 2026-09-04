"""Compiling a whole project into one continuous recap video.

Phase 1 makes sure every chapter has its own finished MP4 - kept, not a
throwaway intermediate, so a later BGM/volume-only change can rebuild just
the mix and that file instead of re-running TTS and frame compositing.
Phase 2 joins them by rebuilding one continuous timeline (see timeline.py)
and encoding it in a single ffmpeg pass.

The join itself needs an explicit --force to rebuild: detecting "did
anything downstream change" across every chapter at once isn't worth the
complexity for an occasional whole-manga operation, while each per-chapter
step already resumes and re-renders on its own."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from remanga.audio.mix import AudioProcessor
from remanga.audio.tts import TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.full_recap.discovery import discover_chapters
from remanga.full_recap.timeline import assemble_combined_audio
from remanga.humanize import fmt_duration
from remanga.paths import get_chapter_dir, get_final_video_path, get_full_recap_concat_path, get_full_recap_video_path
from remanga.video.compose import FrameCompositor
from remanga.video.render import VideoRenderer


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

    def compile_full_manga(
        self, project_name: str, force: bool = False, chapters: Optional[List[str]] = None,
        force_chapters: Optional[bool] = None,
    ) -> Path:
        """force controls both "recompile the join even if already compiled"
        and, by default, "force each chapter's own render too". Pass
        force_chapters=False explicitly to keep the first meaning while
        skipping redundant per-chapter re-renders - e.g. remix.py's rejoin,
        where every chapter was just freshly mixed/rendered a moment ago and
        forcing them again would just repeat identical ffmpeg work; the
        per-chapter render's own mtime-staleness check (see
        video/render.py) still catches any chapter that's actually stale."""
        if force_chapters is None:
            force_chapters = force
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
            chapter_videos.append(self._ensure_chapter_video(project_name, chapter_num, force=force_chapters))

        # Phase 2: the whole-manga join - a fresh continuous audio timeline
        # (see timeline.assemble_combined_audio's docstring for why this can't just
        # reuse the per-chapter mixed audio from phase 1) plus one concat
        # list spanning every chapter's frames in order.
        master_audio_path, frame_timeline = assemble_combined_audio(self.config, project_name, chapter_list)
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

        total_video_sec = sum(d for _, d in frame_timeline)
        result = run_ffmpeg(cmd, capture=True, show_progress=True, total_seconds=total_video_sec,
                            description="Encoding full-manga recap")
        if result.returncode != 0:
            console.print(f"[red]FFmpeg Error Details:\n{_esc(result.stderr)}[/]")
            raise RuntimeError("FFmpeg full-manga rendering failed.")

        elapsed_sec = time.perf_counter() - start_time
        console.print(f"[bold green]✓ Full-manga recap compiled successfully![/] "
                       f"[dim]({len(chapter_list)} chapters, {fmt_duration(total_video_sec)} runtime, "
                       f"{fmt_duration(elapsed_sec)} to compile)[/]")
        console.print(f"[bold green]Location:[/] {_esc(str(final_video))}")
        console.print(f"[dim]Per-chapter videos kept at:[/] {_esc(str(get_final_video_path(project_name, chapter_list[0]).parent.parent))}/*/")
        return final_video


