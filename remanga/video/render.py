from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console

from remanga.config import SystemConfig, VideoConfig
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json
from remanga.paths import get_chapter_dir
from remanga.video.compose import FrameCompositor

console = Console()


class VideoRenderer:
    def __init__(self, system_config: Optional[SystemConfig] = None, video_config: Optional[VideoConfig] = None):
        self.system_config = system_config or SystemConfig()
        self.video_config = video_config or VideoConfig()
        self.compositor = FrameCompositor(self.video_config)

    def _test_gpu_encoder(self) -> bool:
        """Checks if configured NVENC GPU encoder is operational."""
        if not self.system_config.prefer_gpu:
            return False
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1", "-c:v", self.system_config.gpu_codec, "-f", "null", "-"]
        try:
            res = run_ffmpeg(cmd)
            return res.returncode == 0
        except Exception:
            return False

    def render_video(self, project_name: str, chapter_num: str, force: bool = False) -> Path:
        """
        Composites frames, synchronizes with master audio,
        and renders final MP4 with GPU acceleration (or fallback CPU encoder).
        """
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        timing_path = chapter_dir / "audio_timing.json"
        master_audio = chapter_dir / "master_audio.wav"
        video_dir = chapter_dir / "video"
        final_video = chapter_dir / f"{project_name}_ch{chapter_num}_recap.mp4"

        if not force and final_video.exists() and final_video.stat().st_size > 1000:
            console.print(f"[bold green]✓ Recap video already rendered:[/] {final_video}")
            return final_video

        if not master_audio.exists():
            raise FileNotFoundError(f"Master audio not found: {master_audio}")

        # 1. Composite frames to canvas
        self.compositor.prepare_composited_frames(project_name, chapter_num, force=force)

        # 2. Create FFmpeg Concat Script
        timing_info = read_json(timing_path)

        panels = timing_info.get("panels", [])
        concat_file = video_dir / "concat_list.txt"

        with open(concat_file, "w", encoding="utf-8") as f:
            for p in panels:
                panel_id = p["panel_id"]
                frame_file = video_dir / "frames" / f"frame_{panel_id}.png"
                duration = p["total_slot_sec"]
                f.write(f"file '{frame_file.resolve()}'\n")
                f.write(f"duration {duration}\n")
            if panels:
                last_frame = video_dir / "frames" / f"frame_{panels[-1]['panel_id']}.png"
                f.write(f"file '{last_frame.resolve()}'\n")

        # 3. Select Video Codec (GPU NVENC vs CPU libx264)
        use_gpu = self._test_gpu_encoder()
        codec = self.system_config.gpu_codec if use_gpu else self.system_config.fallback_codec
        console.print(f"[cyan]Rendering video using codec:[/] [bold]{codec}[/] [dim]({'Hardware GPU' if use_gpu else 'CPU fallback'})[/]")

        # 4. Build FFmpeg Command
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
        result = run_ffmpeg(cmd, capture=True)

        if result.returncode != 0:
            console.print(f"[red]FFmpeg Error Details:\n{result.stderr}[/]")
            raise RuntimeError("FFmpeg rendering failed.")

        console.print(f"[bold green]✓ Recap video generated successfully![/]")
        console.print(f"[bold green]Location:[/] {final_video}")
        return final_video