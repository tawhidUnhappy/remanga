"""Video settings - see remanga/video/render.py and compose.py."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from remanga.config.base import ConfigModel


def _was(name: str, old: str) -> AliasChoices:
    return AliasChoices(name, old)


class VideoConfig(ConfigModel):
    width: int = 1920
    height: int = 1080
    fps: int = 24
    background_style: str = "blur"  # 'blur' (the page, blurred and dimmed) or 'solid' (background_color)
    blur_brightness: float = 0.42   # dimming of the blurred background (0.35 to 0.55 recommended)
    background_color: str = "#000000"
    page_padding_percent: int = Field(4, validation_alias=_was("page_padding_percent", "panel_padding_percent"))
    auto_adaptive_padding: bool = True
    # How much a panel may be enlarged to fill the frame. Panels are cut at
    # the page's own resolution, so a small panel on a 4K canvas would
    # otherwise be blown up four or five times and look soft - there is
    # nothing in the source to fill those pixels with. Capped, a small panel
    # simply sits smaller on screen, sharp, with more of the blurred
    # background around it. 0 or less means no cap (fill the frame).
    max_upscale: float = 3.0
    # An intro played before every recap (video/intro.py), chosen in Settings
    # like the background music from global/intro/. Off by default. Not part
    # of the picture fingerprint - changing it re-joins, never re-encodes.
    intro_enabled: bool = False
    intro_path: str = ""
    page_border_width: int = Field(2, validation_alias=_was("page_border_width", "panel_border_width"))
    page_border_color: str = Field("#222222", validation_alias=_was("page_border_color", "panel_border_color"))
