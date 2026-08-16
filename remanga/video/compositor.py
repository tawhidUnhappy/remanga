from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageColor
from rich.console import Console

from remanga.config import VideoConfig, get_chapter_dir

console = Console()


class FrameCompositor:
    def __init__(self, config: Optional[VideoConfig] = None):
        self.config = config or VideoConfig()
        self.canvas_size = (self.config.width, self.config.height)
        self.bg_color = ImageColor.getrgb(self.config.background_color)

    def fit_image_on_canvas(self, image_path: Path, output_path: Path) -> Path:
        """
        Loads a cropped panel, calculates proportional fit within canvas
        considering padding, centers it on a solid black background, and exports.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img_w, img_h = img.size

            # Usable canvas dimensions after applying configured padding percent
            pad_factor = 1.0 - (self.config.panel_padding_percent * 2 / 100.0)
            max_w = int(self.config.width * pad_factor)
            max_h = int(self.config.height * pad_factor)

            # Compute uniform scaling factor
            scale = min(max_w / img_w, max_h / img_h)
            new_w = max(1, int(img_w * scale))
            new_h = max(1, int(img_h * scale))

            # High-quality Lanczos scaling
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Create solid color background canvas
            canvas = Image.new("RGB", self.canvas_size, self.bg_color)

            # Center position
            offset_x = (self.config.width - new_w) // 2
            offset_y = (self.config.height - new_h) // 2

            canvas.paste(resized_img, (offset_x, offset_y))
            canvas.save(output_path, "PNG", optimize=True)

        return output_path

    def prepare_composited_frames(self, project_name: str, chapter_num: str) -> Path:
        """Processes all cropped panels into full-resolution canvas frames."""
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        panels_dir = chapter_dir / "panels"
        frames_dir = chapter_dir / "video" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        panels = sorted(list(panels_dir.glob("panel_*.png")) + list(panels_dir.glob("panel_*.jpg")))
        if not panels:
            raise FileNotFoundError(f"No cropped panels found in: {panels_dir}")

        console.print(f"[cyan]Compositing {len(panels)} panels onto {self.config.width}x{self.config.height} black canvas...[/]")
        for p in panels:
            out_frame = frames_dir / f"frame_{p.stem}.png"
            self.fit_image_on_canvas(p, out_frame)

        return frames_dir