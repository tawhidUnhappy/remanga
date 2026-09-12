from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from rich.progress import BarColumn, Progress, TextColumn

from remanga.config import VideoConfig
from remanga.console import console
from remanga.paths import get_chapter_dir, get_video_frames_dir

# Compression for the composited frame PNGs. They're a private, lossless
# cache the encoder reads once per panel - never a deliverable - so a smaller
# file buys nothing. optimize=True (maximum zlib effort) was 589ms of the
# 648ms a 1080p frame took, and on the blurred background it saved nothing:
# level 1 wrote 1006KB in 57ms, optimize 1034KB.
_FRAME_PNG_COMPRESS_LEVEL = 1


class FrameCompositor:
    def __init__(self, config: VideoConfig | None = None):
        self.config = config or VideoConfig()
        self.canvas_size = (self.config.width, self.config.height)
        self.bg_color = ImageColor.getrgb(self.config.background_color)
        self.border_color = ImageColor.getrgb(getattr(self.config, "panel_border_color", "#222222"))

    def _create_fast_canvas_blur(self, src_img: Image.Image) -> Image.Image:
        """
        CapCut-Style Ultra-Fast Canvas Bokeh Blur:
        Downsamples to 64x36, applies a tiny blur kernel, dims, and upscales to full canvas.

        Everything that can happen at 64x36 does. The fill-crop is taken as
        a box in the panel's own coordinates, so the panel goes to the
        thumbnail in ONE resample - it used to be blown up to cover the whole
        canvas first (a 600x1200 panel became a 1920x3840 image) only to be
        shrunk straight back down. Dimming is a per-pixel multiply, so it
        commutes with the upscale and costs 2,304 pixels instead of
        2,073,600. Measured over all 1,487 panels on disk: 46.6ms -> 13.7ms
        per frame, pixel difference from the old path at most 6 of 255.
        """
        cw, ch = self.canvas_size
        iw, ih = src_img.size

        # 1. The centered region of the panel a fill-crop would keep. Clamped
        # because the float arithmetic lands a hair outside the panel when its
        # aspect already matches the canvas (-1e-13), and resize() rejects a
        # box that leaves the image by any amount.
        scale = max(cw / iw, ch / ih)
        box_w, box_h = cw / scale, ch / scale
        left, top = max(0.0, (iw - box_w) / 2), max(0.0, (ih - box_h) / 2)
        box = (left, top, min(float(iw), left + box_w), min(float(ih), top + box_h))

        # 2. Straight to a tiny thumbnail for instantaneous blur computation
        tiny = src_img.resize((64, 36), Image.Resampling.BILINEAR, box=box)
        tiny = tiny.filter(ImageFilter.GaussianBlur(radius=2))

        # 3. Brightness dimming so the foreground panel pops clearly
        dim_factor = max(0.1, min(1.0, getattr(self.config, "blur_brightness", 0.42)))
        tiny = ImageEnhance.Brightness(tiny).enhance(dim_factor)

        # 4. Upscale back to full canvas
        return tiny.resize((cw, ch), Image.Resampling.BICUBIC)


    def _calculate_adaptive_bounds(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """
        Calculates recommended adaptive margins per panel aspect ratio:
        - Wide tiers: maximizes horizontal width while preserving breathing gutters.
        - Vertical splashes: maintains safe vertical headroom, centered on screen.
        """
        cw, ch = self.canvas_size
        aspect = img_w / max(1, img_h)

        top_margin = 36
        bottom_margin = 36
        side_margin = 48

        avail_w = cw - (side_margin * 2)
        avail_h = ch - (top_margin + bottom_margin)

        # Adaptive fitting
        if aspect > 1.6:
            # Wide landscape panel
            fit_scale = min(avail_w / img_w, avail_h / img_h)
        elif aspect < 0.9:
            # Tall portrait panel
            fit_scale = min(avail_w / img_w, avail_h / img_h)
        else:
            # Standard square / 4:3 panel
            fit_scale = min((avail_w * 0.95) / img_w, avail_h / img_h)

        new_w = max(1, int(img_w * fit_scale))
        new_h = max(1, int(img_h * fit_scale))

        offset_x = (cw - new_w) // 2
        offset_y = top_margin + (avail_h - new_h) // 2

        return (new_w, new_h, offset_x, offset_y)

    def fit_image_on_canvas(self, image_path: Path, output_path: Path) -> Path:
        """Composites foreground panel over blurred/solid canvas with adaptive margins."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(image_path) as raw_img:
            raw_img = ImageOps.exif_transpose(raw_img)
            img = raw_img.convert("RGB")
            img_w, img_h = img.size

            # 1. Background Selection (CapCut-style Fast Blur vs Solid Black)
            bg_style = getattr(self.config, "background_style", "blur")
            if bg_style == "blur":
                canvas = self._create_fast_canvas_blur(img)
            else:
                canvas = Image.new("RGB", self.canvas_size, self.bg_color)

            # 2. Adaptive Sizing & Positioning
            if getattr(self.config, "auto_adaptive_padding", True):
                new_w, new_h, offset_x, offset_y = self._calculate_adaptive_bounds(img_w, img_h)
            else:
                pad_factor = 1.0 - (self.config.panel_padding_percent * 2 / 100.0)
                max_w = int(self.config.width * pad_factor)
                max_h = int(self.config.height * pad_factor)
                scale = min(max_w / img_w, max_h / img_h)
                new_w = max(1, int(img_w * scale))
                new_h = max(1, int(img_h * scale))
                offset_x = (self.config.width - new_w) // 2
                offset_y = (self.config.height - new_h) // 2

            # High-quality Lanczos scaling for foreground panel
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # 3. Draw subtle border around foreground panel for crisp separation
            border_w = getattr(self.config, "panel_border_width", 2)
            if border_w > 0:
                draw = ImageDraw.Draw(canvas)
                draw.rectangle(
                    [
                        offset_x - border_w, offset_y - border_w,
                        offset_x + new_w + border_w - 1, offset_y + new_h + border_w - 1,
                    ],
                    outline=self.border_color,
                    width=border_w
                )

            # 4. Paste foreground panel
            canvas.paste(resized_img, (offset_x, offset_y))

            # Written beside the target and renamed into place. A frame is
            # reused whenever it's over 1000 bytes (prepare_composited_frames),
            # which a PNG cut off by Ctrl+C mid-write easily is.
            partial = output_path.with_name(output_path.name + ".part")
            canvas.save(partial, "PNG", compress_level=_FRAME_PNG_COMPRESS_LEVEL)
            partial.replace(output_path)

        return output_path

    def prepare_composited_frames(self, project_name: str, chapter_num: str, force: bool = False) -> Path:
        """Processes all cropped panels into full-resolution canvas frames."""
        panels_dir = get_chapter_dir(project_name, chapter_num) / "panels"
        frames_dir = get_video_frames_dir(project_name, chapter_num)

        panels = sorted(list(panels_dir.glob("*.png")) + list(panels_dir.glob("*.jpg")))
        if not panels:
            raise FileNotFoundError(f"No cropped panels found in: {panels_dir}")

        bg_mode = getattr(self.config, "background_style", "blur")
        console.print(
            f"[cyan]Compositing {len(panels)} panels onto {self.config.width}x{self.config.height} canvas (Mode: "
            f"{bg_mode})...[/]"
        )

        reused_count = 0
        to_composite = []
        for p in panels:
            out_frame = frames_dir / f"frame_{p.stem}.png"
            if not force and out_frame.exists() and out_frame.stat().st_size > 1000:
                reused_count += 1
                continue
            to_composite.append((p, out_frame))

        if to_composite:
            # Every panel is independent, so they're composited in parallel.
            # Threads rather than processes: Pillow releases the GIL for the
            # resize, blur and deflate work that makes up a frame, and on a
            # 159-panel chapter 12 threads (2.60s) matched 12 processes (2.68s)
            # - without pickling config into workers, or a Ctrl+C landing in a
            # dozen processes at once. One at a time it was 14.1s.
            pool = ThreadPoolExecutor(max_workers=min(len(to_composite), os.cpu_count() or 1))
            try:
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.completed}/{task.total} panels"),
                    refresh_per_second=4,
                ) as progress:
                    task = progress.add_task("[yellow]Compositing frames...", total=len(to_composite))
                    futures = [pool.submit(self.fit_image_on_canvas, p, out_frame) for p, out_frame in to_composite]
                    for future in as_completed(futures):
                        future.result()
                        progress.update(task, advance=1)
            finally:
                # On a failure or Ctrl+C, drop the frames still queued instead
                # of compositing the rest of the chapter first.
                pool.shutdown(wait=True, cancel_futures=True)

        if reused_count > 0:
            console.print(f"[dim cyan](Reused {reused_count} existing composited frames)[/]")

        return frames_dir
