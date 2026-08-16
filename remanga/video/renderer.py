from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console

from remanga.config import SystemConfig, VideoConfig, get_chapter_dir
from remanga.video.compositor import FrameCompositor

console = Console()


class VideoRenderer:
    def __init__(self, system_config: Optional[SystemConfig] = None, video_config: Optional[VideoConfig] = None):
        self.system_config = system_config or SystemConfig()
        self.video_config = video_config or VideoConfig()
        self.compositor = FrameCompositor(self.video_config)

    def _format_srt_timestamp(self, seconds: float) -> str:
        """Formats fractional seconds into SRT timestamp HH:MM:SS,mmm."""
        total_ms = int(round(seconds * 1000))
        hours = total_ms // 3600000
        remainder = total_ms % 3600000
        minutes = remainder // 60000
        remainder = remainder % 60000
        secs = remainder // 1000
        millis = remainder % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_srt_subtitles(self, project_name: str, chapter_num: str) -> Path:
        """Generates standard SRT subtitle file aligned with audio timing metadata."""
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        timing_path = chapter_dir / "audio_timing.json"
        srt_path = chapter_dir / "video" / "subtitles.srt"
        srt_path.parent.mkdir(parents=True, exist_ok=True)

        if not timing_path.exists():
            raise FileNotFoundError(f"Missing timing manifest: {timing_path}")

        with open(timing_path, "r", encoding="utf-8") as f:
            timing_info = json.load(f)

        panels = timing_info.get("panels", [])
        srt_lines = []
        entry_idx = 1

        for p in panels:
            text = p.get("text", "").strip()
            if not text:
                continue

            start_sec = p["start_time_sec"]
            end_sec = p["end_time_sec"]

            srt_lines.append(f"{entry_idx}")
            srt_lines.append(f"{self._format_srt_timestamp(start_sec)} --> {self._format_srt_timestamp(end_sec)}")
            srt_lines.append(text)
            srt_lines.append("")
            entry_idx += 1

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))

        return srt_path

    def _test_gpu_encoder(self) -> bool:
        """Checks if configured NVENC GPU encoder is operational."""
        if not self.system_config.prefer_gpu:
            return False
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1", "-c:v", self.system_config.gpu_codec, "-f", "null", "-"]
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return res.returncode == 0
        except Exception:
            return False

    def render_video(self, project_name: str, chapter_num: str) -> Path:
        """
        Composites frames, generates subtitles, synchronizes with master audio,
        and renders final MP4 with GPU acceleration (or fallback CPU encoder).
        """
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        timing_path = chapter_dir / "audio_timing.json"
        master_audio = chapter_dir / "master_audio.wav"
        video_dir = chapter_dir / "video"
        final_video = chapter_dir / f"{project_name}_ch{chapter_num}_recap.mp4"

        if not master_audio.exists():
            raise FileNotFoundError(f"Master audio not found: {master_audio}")

        # 1. Composite frames to solid black canvas
        self.compositor.prepare_composited_frames(project_name, chapter_num)

        # 2. Generate Subtitles
        srt_path = self.generate_srt_subtitles(project_name, chapter_num)

        # 3. Create FFmpeg Concat Script
        with open(timing_path, "r", encoding="utf-8") as f:
            timing_info = json.load(f)

        panels = timing_info.get("panels", [])
        concat_file = video_dir / "concat_list.txt"
        
        with open(concat_file, "w", encoding="utf-8") as f:
            for p in panels:
                panel_id = p["panel_id"]
                frame_file = video_dir / "frames" / f"frame_{panel_id}.png"
                duration = p["total_slot_sec"]
                f.write(f"file '{frame_file.resolve()}'\n")
                f.write(f"duration {duration}\n")
            # Concat demuxer requirement: repeat last file once
            if panels:
                last_frame = video_dir / "frames" / f"frame_{panels[-1]['panel_id']}.png"
                f.write(f"file '{last_frame.resolve()}'\n")

        # 4. Select Video Codec (GPU NVENC vs CPU libx264)
        use_gpu = self._test_gpu_encoder()
        codec = self.system_config.gpu_codec if use_gpu else self.system_config.fallback_codec
        console.print(f"[cyan]Rendering video using codec:[/] [bold]{codec}[/] [dim]({'Hardware GPU' if use_gpu else 'CPU fallback'})[/]")

        # 5. Build FFmpeg Command
        cmd = [
            "ffmpeg", "-y",
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
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            console.print(f"[red]FFmpeg Error Details:\n{result.stderr}[/]")
            raise RuntimeError("FFmpeg rendering failed.")

        console.print(f"[bold green]✓ Recap video generated successfully![/]")
        console.print(f"[bold green]Location:[/] {final_video}")
        return final_video