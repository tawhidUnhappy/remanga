from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from remanga.config import SystemConfig, VideoConfig
from remanga.console import console, escape as _escape_path
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json
from remanga.paths import get_audio_timing_path, get_final_video_path, get_master_audio_path, get_video_concat_path, get_video_frames_dir
from remanga.venvs import REPO_ROOT
from remanga.video.compose import FrameCompositor


class VideoRenderer:
    def __init__(self, system_config: Optional[SystemConfig] = None, video_config: Optional[VideoConfig] = None):
        self.system_config = system_config or SystemConfig()
        self.video_config = video_config or VideoConfig()
        self.compositor = FrameCompositor(self.video_config)

    def _probe_nvenc(self, ffmpeg_bin: str) -> subprocess.CompletedProcess:
        # A too-small test frame fails NVENC's own minimum-dimension check even
        # when the encoder is otherwise fully working ("Frame Dimension less
        # than the minimum supported value") - indistinguishable from a real
        # failure unless the test frame is comfortably above that floor.
        # 256x256 clears it with real margin while still encoding instantly.
        cmd = [ffmpeg_bin, "-y", "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.1", "-c:v", self.system_config.gpu_codec, "-f", "null", "-"]
        return run_ffmpeg(cmd, capture=True)

    def _probe_error_summary(self, stderr: str) -> str:
        """Pulls out just the encoder's own diagnostic lines from a failed
        probe's stderr - e.g. "[h264_nvenc @ 0x...] Driver does not support
        the required nvenc API version." - instead of the generic filter-graph
        teardown noise ("Terminating thread with error: ...", "Nothing was
        written...") that surrounds it and says nothing about the actual
        cause. Falls back to the last couple of lines if nothing matches."""
        tag = f"[{self.system_config.gpu_codec} @ "
        matches = [ln.strip() for ln in stderr.splitlines() if ln.strip().startswith(tag)]
        if matches:
            return " / ".join(m.split("]", 1)[1].strip() for m in matches)
        return " / ".join(stderr.strip().splitlines()[-2:]) or "unknown error"

    def _find_system_ffmpeg(self) -> Optional[str]:
        """The first `ffmpeg` on PATH that ISN'T remanga's own isolated bin/ffmpeg -
        run.sh prepends bin/ to PATH, so a plain shutil.which("ffmpeg") always
        resolves to that one first. Returns whatever the OS/package manager
        already has installed, if anything - used as a fallback GPU-encoding
        path only (see _resolve_gpu_ffmpeg); every other ffmpeg call in the
        pipeline keeps using the isolated binary, so this doesn't compromise
        the "leaves zero footprint" guarantee - nothing is installed, only an
        already-present system binary is optionally read from."""
        isolated_dir = str((REPO_ROOT / "bin").resolve())
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            if not path_dir or str(Path(path_dir).resolve()) == isolated_dir:
                continue
            candidate = shutil.which("ffmpeg", path=path_dir)
            if candidate:
                return candidate
        return None

    def _resolve_gpu_ffmpeg(self) -> tuple[Optional[str], str]:
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
                    f"the bundled ffmpeg's {self.system_config.gpu_codec} didn't work here "
                    f"({bundled_error}) - using the system ffmpeg ({system_ffmpeg}) instead, which does"
                )
                return system_ffmpeg, note

        return None, f"falling back to CPU - {self.system_config.gpu_codec} didn't work: {bundled_error}"

    def render_video(self, project_name: str, chapter_num: str, force: bool = False) -> Path:
        """
        Composites frames, synchronizes with master audio,
        and renders final MP4 with GPU acceleration (or fallback CPU encoder).
        """
        timing_path = get_audio_timing_path(project_name, chapter_num)
        master_audio = get_master_audio_path(project_name, chapter_num)
        frames_dir = get_video_frames_dir(project_name, chapter_num)
        # Final MP4 lives at {manga}/video/chapter_N/ - see remanga.paths.
        final_video = get_final_video_path(project_name, chapter_num)

        # Rebuild if missing/forced, OR if master_audio.wav is newer than the
        # last render - the case that matters most: the user only changed
        # BGM/volume and re-ran `mix`, so the video needs a fresh encode of
        # this (cheap) step even though nobody passed --force. TTS and frame
        # compositing are untouched either way - see prepare_composited_frames
        # below, which stays a no-op for every already-cached frame.
        stale_audio = final_video.exists() and master_audio.exists() and master_audio.stat().st_mtime > final_video.stat().st_mtime
        if not force and final_video.exists() and final_video.stat().st_size > 1000 and not stale_audio:
            console.print(f"[bold green]✓ Recap video already rendered:[/] {_escape_path(str(final_video))}")
            return final_video
        if stale_audio:
            console.print("[dim]master_audio.wav is newer than the last render (BGM/volume likely changed) - re-encoding video only.[/]")

        if not master_audio.exists():
            raise FileNotFoundError(f"Master audio not found: {master_audio}")

        # 1. Composite frames to canvas
        self.compositor.prepare_composited_frames(project_name, chapter_num, force=force)

        # 2. Create FFmpeg Concat Script
        timing_info = read_json(timing_path)

        panels = timing_info.get("panels", [])
        concat_file = get_video_concat_path(project_name, chapter_num)

        with open(concat_file, "w", encoding="utf-8") as f:
            for p in panels:
                panel_id = p["panel_id"]
                frame_file = frames_dir / f"frame_{panel_id}.png"
                duration = p["total_slot_sec"]
                f.write(f"file '{frame_file.resolve()}'\n")
                f.write(f"duration {duration}\n")
            if panels:
                last_frame = frames_dir / f"frame_{panels[-1]['panel_id']}.png"
                f.write(f"file '{last_frame.resolve()}'\n")

        # 3. Select Video Codec (GPU NVENC vs CPU libx264) and which ffmpeg binary
        # actually has a working GPU encoder on this machine right now (see
        # _resolve_gpu_ffmpeg - not necessarily the bundled one).
        gpu_ffmpeg, note = self._resolve_gpu_ffmpeg()
        use_gpu = gpu_ffmpeg is not None
        codec = self.system_config.gpu_codec if use_gpu else self.system_config.fallback_codec
        ffmpeg_bin = gpu_ffmpeg or "ffmpeg"
        console.print(f"[cyan]Rendering video using codec:[/] [bold]{codec}[/] [dim]({'Hardware GPU' if use_gpu else 'CPU fallback'})[/]")
        if note:
            console.print(f"[dim]({note})[/]")

        # 4. Build FFmpeg Command
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-i", str(master_audio),
            "-vf", f"fps={self.video_config.fps},format=yuv420p",
            "-c:v", codec,
        ]

        if not use_gpu:
            cmd.extend(["-preset", "medium", "-crf", "19", "-threads", str(self.system_config.threads)])
        else:
            cmd.extend(["-preset", "p6", "-cq", "20"])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(final_video)
        ])

        console.print("[yellow]Starting video rendering... This may take a moment.[/]")
        result = run_ffmpeg(cmd, capture=True, show_progress=True)

        if result.returncode != 0:
            console.print(f"[red]FFmpeg Error Details:\n{_escape_path(result.stderr)}[/]")
            raise RuntimeError("FFmpeg rendering failed.")

        console.print(f"[bold green]✓ Recap video generated successfully![/]")
        console.print(f"[bold green]Location:[/] {_escape_path(str(final_video))}")
        return final_video