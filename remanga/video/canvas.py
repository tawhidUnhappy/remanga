"""One panel on one video frame: the blurred (or solid) background, the panel
fitted over it, and how much it had to be scaled to get there.

The scaling is the interesting part. A panel is cut at the page's own
resolution, so it can be anything from a stamp to bigger than the video: it
is fitted inside adaptive margins, and never enlarged past
`video.max_upscale` - a small panel blown up to fill a 4K frame has nothing
to fill it with and only looks soft."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from remanga.config import VideoConfig

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


    def _capped(self, scale: float) -> float:
        """`scale`, never enlarging a panel more than video.max_upscale - see
        that setting for why a blown-up panel is worse than a small one."""
        cap = getattr(self.config, "max_upscale", 0) or 0
        return min(scale, cap) if cap > 0 else scale

    def scale_for(self, img_w: int, img_h: int) -> float:
        """How much a panel this size is scaled to fit the video - under 1.0
        means it is shown smaller than it is, and detail is lost."""
        if getattr(self.config, "auto_adaptive_padding", True):
            new_w, _, _, _ = self._calculate_adaptive_bounds(img_w, img_h)
            return new_w / max(1, img_w)
        pad_factor = 1.0 - (self.config.page_padding_percent * 2 / 100.0)
        return self._capped(min(int(self.config.width * pad_factor) / max(1, img_w),
                                int(self.config.height * pad_factor) / max(1, img_h)))

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

        fit_scale = self._capped(fit_scale)
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
                scale = self._capped(min(max_w / img_w, max_h / img_h))
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
