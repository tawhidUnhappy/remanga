"""Video rendering settings - see remanga/video/render.py and compose.py."""

from __future__ import annotations

from remanga.config.base import ConfigModel


class VideoConfig(ConfigModel):
    width: int = 1920
    height: int = 1080
    # A recap is a slideshow - no frame differs from the one before it until
    # the panel changes - so the rate only decides how finely a panel change
    # can be timed, and every change is snapped into the silent pause before
    # its line anyway (video/frame_timeline.py). Which means almost any rate
    # looks identical, and the choice is really about what everything
    # downstream expects: 24 is the standard video rate, and players, editors
    # and platform encoders all handle it without comment, where a single
    # digit rate is unusual enough to be treated as an error case.
    #
    # The cost is frames that are duplicates of each other, and it is small:
    # they compress to almost nothing between the forced keyframes at each
    # panel change, and on a real 71-panel chapter the measured encode was
    # still well under a minute (video/encoding.py). Dropping to 5 is a
    # legitimate choice if encode time on a CPU-only machine is the problem -
    # nothing in the pipeline assumes either number.
    fps: int = 24
    background_style: str = "blur"  # 'blur' (Fast bokeh blur) or 'solid' (black canvas)
    blur_brightness: float = 0.42   # Dimming multiplier for canvas blur (0.35 to 0.55 recommended)
    background_color: str = "#000000"
    panel_padding_percent: int = 4
    auto_adaptive_padding: bool = True
    panel_border_width: int = 2
    panel_border_color: str = "#222222"
