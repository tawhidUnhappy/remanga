"""The chapter's frames on disk: one composited PNG per narrated panel, built
once and reused.

A frame is reused while its panel is older than it AND the video settings are
the ones it was built with (frames_settings.json) - without that second half a
new size or background would be picked up by the encoder and not by the
pictures it encodes, and the video would come out at the old size."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from remanga import activity
from remanga.console import console
from remanga.json_io import read_json_or, write_json
from remanga.paths import get_panels_dir, get_video_frames_dir
from remanga.video.canvas import FrameCompositor
from remanga.video.quality import quality_warning

# What the frames beside it were composited with. Without this a frame was
# reused whenever the panel hadn't changed, so a new size or background was
# picked up by the encoder and not by the pictures it encoded - the video came
# out at the old size (user report).
FRAMES_SETTINGS_NAME = "frames_settings.json"


class FrameCache(FrameCompositor):
    """A compositor that also knows which frames are already on disk."""

    def prepare_composited_frames(self, project_name: str, chapter_num: str, panel_ids: list[str],
                                  force: bool = False) -> Path:
        """Every narrated panel as a full canvas frame, reusing a frame that is
        already there and newer than its panel."""
        panels_dir = get_panels_dir(project_name, chapter_num, create=False)
        frames_dir = get_video_frames_dir(project_name, chapter_num)
        frames_dir.mkdir(parents=True, exist_ok=True)
        by_stem = {p.stem: p for p in panels_dir.iterdir() if p.is_file()} if panels_dir.exists() else {}
        missing = [panel_id for panel_id in panel_ids if panel_id not in by_stem]
        if missing:
            raise FileNotFoundError(f"Panel image(s) not found in {panels_dir}: {', '.join(missing)}")

        settings_path = frames_dir / FRAMES_SETTINGS_NAME
        settings = self.config.model_dump()
        if read_json_or(settings_path, None) != settings:
            force = True  # a changed video setting is a different picture

        reused_count = 0
        to_composite = []
        for panel_id in panel_ids:
            panel, out_frame = by_stem[panel_id], frames_dir / f"frame_{panel_id}.png"
            if (not force and out_frame.exists() and out_frame.stat().st_size > 1000
                    and out_frame.stat().st_mtime >= panel.stat().st_mtime):
                reused_count += 1
                continue
            to_composite.append((panel, out_frame))

        if to_composite:
            console.print(f"[cyan]Composing {len(to_composite)} panel frame(s) at {self.config.width}x"
                          f"{self.config.height} ({self.config.background_style} background)...[/]")
            # Threads: Pillow releases the GIL for the resize, blur and deflate
            # work that makes up a frame.
            pool = ThreadPoolExecutor(max_workers=min(len(to_composite), os.cpu_count() or 1))
            try:
                with activity.progress("Composing panel frames", total=len(to_composite), unit="panels") as bar:
                    futures = [pool.submit(self.fit_image_on_canvas, panel, out) for panel, out in to_composite]
                    for future in as_completed(futures):
                        future.result()
                        bar.advance()
            finally:
                pool.shutdown(wait=True, cancel_futures=True)

        if reused_count > 0:
            console.print(f"[dim cyan](Reused {reused_count} existing panel frames)[/]")
        warning = quality_warning([panel for panel in by_stem.values() if panel.stem in set(panel_ids)], self.config)
        if warning:
            console.print(f"[yellow]{warning}[/]")
        write_json(settings_path, settings)
        return frames_dir
