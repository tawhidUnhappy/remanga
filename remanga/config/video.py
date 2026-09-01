"""Video rendering settings - see remanga/video/render.py and compose.py."""

from __future__ import annotations

from pydantic import BaseModel


class VideoConfig(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: int = 30
    background_style: str = "blur"  # 'blur' (Fast bokeh blur) or 'solid' (black canvas)
    blur_brightness: float = 0.42   # Dimming multiplier for canvas blur (0.35 to 0.55 recommended)
    background_color: str = "#000000"
    panel_padding_percent: int = 4
    auto_adaptive_padding: bool = True
    panel_border_width: int = 2
    panel_border_color: str = "#222222"
