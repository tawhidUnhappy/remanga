"""Video rendering settings - see remanga/video/render.py and compose.py."""

from __future__ import annotations

from remanga.config.base import ConfigModel


class VideoConfig(ConfigModel):
    width: int = 1920
    height: int = 1080
    # A recap is a slideshow - no frame differs from the one before it until
    # the panel changes - so the rate only decides how finely a panel change
    # can be timed, and every change is snapped into the silent pause before
    # its line anyway (video/frame_timeline.py). 5 encodes 6x fewer frames
    # than 30 for the same picture; raise it only if something ever moves.
    fps: int = 5
    background_style: str = "blur"  # 'blur' (Fast bokeh blur) or 'solid' (black canvas)
    blur_brightness: float = 0.42   # Dimming multiplier for canvas blur (0.35 to 0.55 recommended)
    background_color: str = "#000000"
    panel_padding_percent: int = 4
    auto_adaptive_padding: bool = True
    panel_border_width: int = 2
    panel_border_color: str = "#222222"
