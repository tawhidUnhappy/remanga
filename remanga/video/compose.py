from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from remanga import activity
from remanga.config import VideoConfig
from remanga.console import console
from remanga.json_io import read_json_or, write_json
from remanga.paths import get_pages_dir, get_video_frames_dir

# What the frames beside it were composited with. Without this a frame was
# reused whenever the page hadn't changed, so a new size or background was
# picked up by the encoder and not by the pictures it encoded - the video came
# out at the old size (user report).
FRAMES_SETTINGS_NAME = "frames_settings.json"

# Compression for the composited frame PNGs. They're a private, lossless
# cache the encoder reads once per page - never a deliverable - so a smaller
# file buys nothing. optimize=True (maximum zlib effort) was 589ms of the
# 648ms a 1080p frame took, and on the blurred background it saved nothing:
# level 1 wrote 1006KB in 57ms, optimize 1034KB.
_FRAME_PNG_COMPRESS_LEVEL = 1


class FrameCompositor:
    def __init__(self, config: VideoConfig | None = None):
        self.config = config or VideoConfig()
        self.canvas_size = (self.config.width, self.config.height)
        self.bg_color = ImageColor.getrgb(self.config.background_color)
        self.border_color = ImageColor.getrgb(self.config.page_border_color)

    def _create_fast_canvas_blur(self, src_img: Image.Image) -> Image.Image:
        """
        CapCut-Style Ultra-Fast Canvas Bokeh Blur:
        Downsamples to 64x36, applies a tiny blur kernel, dims, and upscales to full canvas.

        Everything that can happen at 64x36 does. The fill-crop is taken as
        a box in the page's own coordinates, so the page goes to the
        thumbnail in one resample instead of being blown up to canvas size first. Dimming is a per-pixel multiply, so it
        commutes with the upscale and costs 2,304 pixels instead of
        2,073,600.
        """
        cw, ch = self.canvas_size
        iw, ih = src_img.size

        # 1. The centered region of the page a fill-crop would keep. Clamped
        # because the float arithmetic lands a hair outside the page when its
        # aspect already matches the canvas (-1e-13), and resize() rejects a
        # box that leaves the image by any amount.
        scale = max(cw / iw, ch / ih)
        box_w, box_h = cw / scale, ch / scale
        left, top = max(0.0, (iw - box_w) / 2), max(0.0, (ih - box_h) / 2)
        box = (left, top, min(float(iw), left + box_w), min(float(ih), top + box_h))

        # 2. Straight to a tiny thumbnail for instantaneous blur computation
        tiny = src_img.resize((64, 36), Image.Resampling.BILINEAR, box=box)
        tiny = tiny.filter(ImageFilter.GaussianBlur(radius=2))

        # 3. Brightness dimming so the foreground page pops clearly
        dim_factor = max(0.1, min(1.0, getattr(self.config, "blur_brightness", 0.42)))
        tiny = ImageEnhance.Brightness(tiny).enhance(dim_factor)

        # 4. Upscale back to full canvas
        return tiny.resize((cw, ch), Image.Resampling.BICUBIC)


    def _calculate_adaptive_bounds(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """
        Adaptive margins by the page's aspect ratio:
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
            # Wide landscape page
            fit_scale = min(avail_w / img_w, avail_h / img_h)
        elif aspect < 0.9:
            # Tall portrait page
            fit_scale = min(avail_w / img_w, avail_h / img_h)
        else:
            # Standard square / 4:3 page
            fit_scale = min((avail_w * 0.95) / img_w, avail_h / img_h)

        new_w = max(1, int(img_w * fit_scale))
        new_h = max(1, int(img_h * fit_scale))

        offset_x = (cw - new_w) // 2
        offset_y = top_margin + (avail_h - new_h) // 2

        return (new_w, new_h, offset_x, offset_y)

    def fit_image_on_canvas(self, image_path: Path, output_path: Path) -> Path:
        """The page over its blurred (or solid) background, with adaptive margins."""
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
                pad_factor = 1.0 - (self.config.page_padding_percent * 2 / 100.0)
                max_w = int(self.config.width * pad_factor)
                max_h = int(self.config.height * pad_factor)
                scale = min(max_w / img_w, max_h / img_h)
                new_w = max(1, int(img_w * scale))
                new_h = max(1, int(img_h * scale))
                offset_x = (self.config.width - new_w) // 2
                offset_y = (self.config.height - new_h) // 2

            # High-quality Lanczos scaling for foreground page
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # 3. Draw subtle border around foreground page for crisp separation
            border_w = self.config.page_border_width
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

            # 4. Paste foreground page
            canvas.paste(resized_img, (offset_x, offset_y))

            # Written beside the target and renamed into place. A frame is
            # reused whenever it's over 1000 bytes (prepare_composited_frames),
            # which a PNG cut off by Ctrl+C mid-write easily is.
            partial = output_path.with_name(output_path.name + ".part")
            canvas.save(partial, "PNG", compress_level=_FRAME_PNG_COMPRESS_LEVEL)
            partial.replace(output_path)

        return output_path

    def prepare_composited_frames(self, project_name: str, chapter_num: str, page_ids: list[str],
                                  force: bool = False) -> Path:
        """Every narrated page as a full canvas frame, reusing a frame that is
        already there and newer than its page."""
        pages_dir = get_pages_dir(project_name, chapter_num)
        frames_dir = get_video_frames_dir(project_name, chapter_num)
        frames_dir.mkdir(parents=True, exist_ok=True)
        by_stem = {p.stem: p for p in pages_dir.iterdir() if p.is_file()} if pages_dir.exists() else {}
        missing = [page_id for page_id in page_ids if page_id not in by_stem]
        if missing:
            raise FileNotFoundError(f"Page image(s) not found in {pages_dir}: {', '.join(missing)}")

        settings_path = frames_dir / FRAMES_SETTINGS_NAME
        settings = self.config.model_dump()
        if read_json_or(settings_path, None) != settings:
            force = True  # a changed video setting is a different picture

        reused_count = 0
        to_composite = []
        for page_id in page_ids:
            page, out_frame = by_stem[page_id], frames_dir / f"frame_{page_id}.png"
            if (not force and out_frame.exists() and out_frame.stat().st_size > 1000
                    and out_frame.stat().st_mtime >= page.stat().st_mtime):
                reused_count += 1
                continue
            to_composite.append((page, out_frame))

        if to_composite:
            console.print(f"[cyan]Composing {len(to_composite)} page frame(s) at {self.config.width}x"
                          f"{self.config.height} ({self.config.background_style} background)...[/]")
            # Threads: Pillow releases the GIL for the resize, blur and deflate
            # work that makes up a frame.
            pool = ThreadPoolExecutor(max_workers=min(len(to_composite), os.cpu_count() or 1))
            try:
                with activity.progress("Composing page frames", total=len(to_composite), unit="pages") as bar:
                    futures = [pool.submit(self.fit_image_on_canvas, page, out) for page, out in to_composite]
                    for future in as_completed(futures):
                        future.result()
                        bar.advance()
            finally:
                pool.shutdown(wait=True, cancel_futures=True)

        if reused_count > 0:
            console.print(f"[dim cyan](Reused {reused_count} existing page frames)[/]")
        write_json(settings_path, settings)
        return frames_dir
