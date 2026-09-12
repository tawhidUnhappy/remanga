from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from remanga.config import SystemConfig, VideoConfig
from remanga.console import console, escape as _escape_path
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json, read_json_or, write_json
from remanga.paths import (
    BIN_DIR,
    get_audio_timing_path,
    get_final_video_path,
    get_master_audio_path,
    get_video_concat_path,
    get_video_frames_dir,
    get_video_picture_path,
    get_video_work_dir,
)
from remanga.verify import ensure_panels_match_narration
from remanga.video.compose import FrameCompositor
from remanga.video.encoding import (
    AUDIO_CODEC_ARGS,
    MUX_ARGS,
    PICTURE_FORMAT_VERSION,
    picture_codec_args,
    picture_filter_args,
)
from remanga.video.frame_timeline import FrameTimeline, build_frame_timeline


class VideoRenderer:
    def __init__(self, system_config: SystemConfig | None = None, video_config: VideoConfig | None = None):
        self.system_config = system_config or SystemConfig()
        self.video_config = video_config or VideoConfig()
        self.compositor = FrameCompositor(self.video_config)
        self._encoder_choice: tuple[str, str, bool, str] | None = None

    def _probe_nvenc(self, ffmpeg_bin: str) -> subprocess.CompletedProcess:
        # A too-small test frame fails NVENC's own minimum-dimension check even
        # when the encoder is otherwise fully working ("Frame Dimension less
        # than the minimum supported value") - indistinguishable from a real
        # failure unless the test frame is comfortably above that floor.
        # 256x256 clears it with real margin while still encoding instantly.
        cmd = [
            ffmpeg_bin, "-y", "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.1",
            "-c:v", self.system_config.resolve_gpu_codec(), "-f", "null", "-",
        ]
        return run_ffmpeg(cmd, capture=True)

    def _probe_error_summary(self, stderr: str) -> str:
        """Pulls out just the encoder's own diagnostic lines from a failed
        probe's stderr - e.g. "[h264_nvenc @ 0x...] Driver does not support
        the required nvenc API version." - instead of the generic filter-graph
        teardown noise ("Terminating thread with error: ...", "Nothing was
        written...") that surrounds it and says nothing about the actual
        cause. Falls back to the last couple of lines if nothing matches."""
        tag = f"[{self.system_config.resolve_gpu_codec()} @ "
        matches = [ln.strip() for ln in stderr.splitlines() if ln.strip().startswith(tag)]
        if matches:
            return " / ".join(m.split("]", 1)[1].strip() for m in matches)
        return " / ".join(stderr.strip().splitlines()[-2:]) or "unknown error"

    def _find_system_ffmpeg(self) -> str | None:
        """The first `ffmpeg` on PATH that ISN'T remanga's own isolated bin/ffmpeg -
        run.sh prepends bin/ to PATH, so a plain shutil.which("ffmpeg") always
        resolves to that one first. Returns whatever the OS/package manager
        already has installed, if anything - used as a fallback GPU-encoding
        path only (see _resolve_gpu_ffmpeg); every other ffmpeg call in the
        pipeline keeps using the isolated binary, so this doesn't compromise
        the "leaves zero footprint" guarantee - nothing is installed, only an
        already-present system binary is optionally read from."""
        isolated_dir = str(BIN_DIR.resolve())
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            if not path_dir or str(Path(path_dir).resolve()) == isolated_dir:
                continue
            candidate = shutil.which("ffmpeg", path=path_dir)
            if candidate:
                return candidate
        return None

    def _resolve_gpu_ffmpeg(self) -> tuple[str | None, str]:
        """Finds an ffmpeg binary whose GPU encoder actually works against the
        driver installed on THIS machine right now, and returns (path, note) -
        note explains why the bundled binary was skipped, if it was, for the
        console message in render_video(); path is None if nothing worked.

        Why the bundled bin/ffmpeg can fail NVENC even with a real, working
        NVIDIA GPU: bootstrap.sh downloads whatever the latest BtbN/FFmpeg-
        Builds master snapshot is, built against whatever NVIDIA NVENC SDK
        version was current that day. NVENC's minimum required driver version
        only ever goes up over time, so a bundled build newer than your last
        driver update can require an NVENC API version your installed driver
        doesn't support yet ("Driver does not support the required nvenc API
        version") - a real environment mismatch, not a bug in this check. A
        distro-packaged system ffmpeg is typically built against far more
        conservative headers and often still works fine on the same driver,
        so it's tried next before giving up on GPU encoding entirely.
        """
        if not self.system_config.prefer_gpu:
            return None, ""

        bundled = shutil.which("ffmpeg")
        if bundled:
            res = self._probe_nvenc(bundled)
            if res.returncode == 0:
                return bundled, ""
            bundled_error = self._probe_error_summary(res.stderr or "")
        else:
            bundled_error = "bundled ffmpeg not found on PATH"

        system_ffmpeg = self._find_system_ffmpeg()
        if system_ffmpeg:
            res = self._probe_nvenc(system_ffmpeg)
            if res.returncode == 0:
                note = (
                    f"the bundled ffmpeg's {self.system_config.resolve_gpu_codec()} didn't work here "
                    f"({bundled_error}) - using the system ffmpeg ({system_ffmpeg}) instead, which does"
                )
                return system_ffmpeg, note

        return None, f"falling back to CPU - {self.system_config.resolve_gpu_codec()} didn't work: {bundled_error}"

    def encoder(self) -> tuple[str, str, bool, str]:
        """(ffmpeg binary, codec, is-GPU, note) - probed once per renderer.
        A full recap asks for every chapter, and the answer shouldn't change
        mid-run anyway: pictures from two different encoders can't be
        stream-copied into one join."""
        if self._encoder_choice is None:
            gpu_ffmpeg, note = self._resolve_gpu_ffmpeg()
            use_gpu = gpu_ffmpeg is not None
            codec = self.system_config.resolve_gpu_codec() if use_gpu else self.system_config.fallback_codec
            self._encoder_choice = (gpu_ffmpeg or "ffmpeg", codec, use_gpu, note)
        return self._encoder_choice

    def frame_timeline(self, project_name: str, chapter_num: str) -> FrameTimeline:
        """This chapter's panels on the configured frame grid (video/frame_timeline.py)."""
        panels = read_json(get_audio_timing_path(project_name, chapter_num)).get("panels", [])
        return build_frame_timeline(panels, self.video_config.fps)

    # --- the picture stream: video only, cached apart from the final MP4 ---

    @staticmethod
    def _picture_fingerprint_path(picture: Path) -> Path:
        return picture.with_name(f"{picture.stem}_fingerprint.json")

    def _picture_fingerprint(self, project_name: str, chapter_num: str, timeline: FrameTimeline) -> dict[str, Any]:
        """Everything that decides what picture.mp4 contains: the timing it
        was laid out from (audio_timing.json is only rewritten when its
        content changes - see audio/tts.py), every video setting, the encoder,
        and the encode recipe itself."""
        return {
            "format": PICTURE_FORMAT_VERSION,
            "timing_mtime": get_audio_timing_path(project_name, chapter_num).stat().st_mtime,
            "codec": self.encoder()[1],
            "total_frames": timeline.total_frames,
            "video": self.video_config.model_dump(),
        }

    def _picture_is_fresh(self, project_name: str, chapter_num: str, timeline: FrameTimeline) -> bool:
        picture = get_video_picture_path(project_name, chapter_num)
        if not picture.exists() or picture.stat().st_size <= 1000:
            return False
        recorded = read_json_or(self._picture_fingerprint_path(picture), None)
        if recorded != self._picture_fingerprint(project_name, chapter_num, timeline):
            return False
        # A frame composited since - deleted and rebuilt - is a different
        # picture even under identical settings.
        built = picture.stat().st_mtime
        frames = get_video_frames_dir(project_name, chapter_num).glob("frame_*.png")
        return not any(frame.stat().st_mtime > built for frame in frames)

    def ensure_picture(self, project_name: str, chapter_num: str, force: bool = False) -> tuple[Path, FrameTimeline]:
        """This chapter's encoded picture stream, encoded only if it's missing
        or stale. A render muxes it with the mixed sound; full-recap
        stream-copies every chapter's picture into the join. Either way, a
        change to the sound alone never re-encodes a frame."""
        timeline = self.frame_timeline(project_name, chapter_num)
        if force or not self._picture_is_fresh(project_name, chapter_num, timeline):
            self._encode_picture(project_name, chapter_num, timeline, force=force)
        return get_video_picture_path(project_name, chapter_num), timeline

    def _encode_picture(
        self, project_name: str, chapter_num: str, timeline: FrameTimeline, *,
        force: bool = False, sound: tuple[Path, Path] | None = None,
    ) -> None:
        """Composites any missing frames and encodes picture.mp4 from them.

        `sound`, as (mixed WAV, AAC to write), encodes the chapter's audio in
        the same ffmpeg run. ffmpeg gives each encoder a thread of its own, so
        a fresh render waits for the slower of the two, not both in turn."""
        if not timeline.total_frames:
            raise RuntimeError(f"audio_timing.json for chapter {chapter_num} lists no panels - nothing to render.")

        # 1. Composite frames to canvas
        self.compositor.prepare_composited_frames(project_name, chapter_num, force=force)

        # 2. Concat script: one entry per panel, snapped to the frame grid
        concat_file = get_video_concat_path(project_name, chapter_num)
        timeline.write_concat_list(concat_file, get_video_frames_dir(project_name, chapter_num))

        # 3. Encoder (GPU NVENC vs CPU libx264) and the ffmpeg binary that has
        # a working GPU encoder on this machine right now (see
        # _resolve_gpu_ffmpeg - not necessarily the bundled one).
        ffmpeg_bin, codec, use_gpu, note = self.encoder()
        console.print(
            f"[cyan]Rendering video using codec:[/] [bold]{codec}[/] "
            f"[dim]({'Hardware GPU' if use_gpu else 'CPU fallback'}, "
            f"{timeline.total_frames} frames at {timeline.fps}fps)[/]"
        )
        if note:
            console.print(f"[dim]({note})[/]")

        # 4. Encode. Written beside the target and renamed into place, so a
        # killed run never leaves a truncated picture that looks finished.
        picture = get_video_picture_path(project_name, chapter_num)
        partial = picture.with_name(f"{picture.stem}.part.mp4")
        cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
        if sound:
            cmd += ["-i", str(sound[0])]
        cmd += ["-map", "0:v:0", *picture_filter_args(timeline),
                *picture_codec_args(codec, use_gpu, self.system_config.threads), str(partial)]
        if sound:
            cmd += ["-map", "1:a:0", *AUDIO_CODEC_ARGS, str(sound[1])]

        # The picture's length is known exactly - it's the timeline it was
        # laid out from - so the bar shows a real percentage.
        result = run_ffmpeg(cmd, capture=True, show_progress=True, total_seconds=timeline.duration_sec,
                            description=f"Encoding {self.video_config.height}p video")
        if result.returncode != 0:
            partial.unlink(missing_ok=True)
            console.print(f"[red]FFmpeg Error Details:\n{_escape_path(result.stderr)}[/]")
            raise RuntimeError("FFmpeg rendering failed.")
        partial.replace(picture)
        # Last: a picture with no fingerprint beside it (a run killed right
        # here) reads as stale and is simply encoded again.
        write_json(self._picture_fingerprint_path(picture),
                   self._picture_fingerprint(project_name, chapter_num, timeline))

    def render_video(self, project_name: str, chapter_num: str, force: bool = False) -> Path:
        """
        Composites frames, synchronizes with master audio,
        and renders final MP4 with GPU acceleration (or fallback CPU encoder).

        The picture (ensure_picture) and the sound are encoded apart and
        stream-copied together at the end, so when only the mix changed the
        cached picture is reused and the render is one audio encode.
        """
        # Refuse to produce output that would be silently degraded - see
        # verify/gate.py. Here rather than in pipeline.py so full-recap,
        # which does not go through the wizard's steps, is covered too.
        ensure_panels_match_narration(project_name, chapter_num, stage="video rendering")

        master_audio = get_master_audio_path(project_name, chapter_num)
        # Final MP4 lives at {manga}/video/chapter_N/ - see remanga.paths.
        final_video = get_final_video_path(project_name, chapter_num)

        # Rebuild if missing/forced, OR if master_audio.wav is newer than the
        # last render - the case that matters most: the user only changed
        # BGM/volume and re-ran `mix`, so the video needs a fresh encode of
        # its sound even though nobody passed --force. TTS, frame compositing
        # and the picture encode are untouched either way - see
        # _picture_is_fresh below.
        stale_audio = (
            final_video.exists() and master_audio.exists()
            and master_audio.stat().st_mtime > final_video.stat().st_mtime
        )
        if not force and final_video.exists() and final_video.stat().st_size > 1000 and not stale_audio:
            console.print(f"[bold green]✓ Recap video already rendered:[/] {_escape_path(str(final_video))}")
            return final_video
        if stale_audio:
            console.print(
                "[dim]master_audio.wav is newer than the last render (BGM/volume likely changed) - rebuilding the "
                "video around it.[/]"
            )

        if not master_audio.exists():
            raise FileNotFoundError(f"Master audio not found: {master_audio}")

        timeline = self.frame_timeline(project_name, chapter_num)
        picture = get_video_picture_path(project_name, chapter_num)
        work_dir = get_video_work_dir(project_name, chapter_num)
        partial = work_dir / f"{final_video.stem}.part.mp4"

        if not force and self._picture_is_fresh(project_name, chapter_num, timeline):
            console.print("[dim](picture unchanged since the last render - reusing it, encoding only the sound)[/]")
            cmd = [
                "ffmpeg", "-y", "-i", str(picture), "-i", str(master_audio),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", *AUDIO_CODEC_ARGS, *MUX_ARGS, str(partial),
            ]
            result = run_ffmpeg(cmd, capture=True, show_progress=True, total_seconds=timeline.duration_sec,
                                description="Encoding audio")
        else:
            sound = work_dir / "sound.part.m4a"
            try:
                self._encode_picture(project_name, chapter_num, timeline, force=force, sound=(master_audio, sound))
                cmd = [
                    "ffmpeg", "-y", "-i", str(picture), "-i", str(sound),
                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", *MUX_ARGS, str(partial),
                ]
                result = run_ffmpeg(cmd, capture=True)
            finally:
                sound.unlink(missing_ok=True)

        if result.returncode != 0:
            partial.unlink(missing_ok=True)
            console.print(f"[red]FFmpeg Error Details:\n{_escape_path(result.stderr)}[/]")
            raise RuntimeError("FFmpeg rendering failed.")
        partial.replace(final_video)

        console.print("[bold green]✓ Recap video generated successfully![/]")
        console.print(f"[bold green]Location:[/] {_escape_path(str(final_video))}")
        return final_video
