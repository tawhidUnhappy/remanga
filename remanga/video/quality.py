"""Whether this video size does the panels justice.

Panels are cut at the page's full resolution, so a panel bigger than the
video is shown smaller than it is and detail is lost for nothing. This says
how many, which is worst, and what size would show them all whole - the
warning the video step prints and the result screen carries."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from remanga.config import VideoConfig
from remanga.video.canvas import FrameCompositor

# Under this much scaling a panel is being shown smaller than it is. Not
# exactly 1.0: a panel a hair over the fit area loses nothing anyone can see,
# and the integer rounding in the fit lands there by itself.
KEEPS_DETAIL_SCALE = 0.98


def downscaled_panels(panels: Sequence[Path], config: VideoConfig) -> list[tuple[Path, float]]:
    """Every panel the video would show smaller than it is, with its scale.
    Only the image headers are read, so this costs nothing next to a render."""
    compositor = FrameCompositor(config)
    smaller = []
    for panel in panels:
        try:
            with Image.open(panel) as image:
                width, height = image.size
        except Exception:  # a broken panel is the renderer's problem to report
            continue
        scale = compositor.scale_for(width, height)
        if scale < KEEPS_DETAIL_SCALE:
            smaller.append((panel, scale))
    return smaller


# The sizes a bigger video is offered in, widescreen and vertical - the same
# ones the Settings screen lists, so the suggestion is something to pick.
VIDEO_SIZES = ((1920, 1080), (2560, 1440), (3840, 2160))


def _big_enough(config: VideoConfig, factor: float) -> str:
    """The smallest offered video size that fits a video `factor` times this
    one, in the same orientation - or the exact size when none is."""
    vertical = config.height > config.width
    for width, height in VIDEO_SIZES:
        if vertical:
            width, height = height, width
        if width >= config.width * factor and height >= config.height * factor:
            return f"{width}x{height}"
    return f"{int(config.width * factor / 2) * 2}x{int(config.height * factor / 2) * 2}"


def quality_warning(panels: Sequence[Path], config: VideoConfig) -> str | None:
    """One sentence about the panels this video size shrinks, or None."""
    smaller = downscaled_panels(panels, config)
    if not smaller:
        return None
    worst_panel, worst = min(smaller, key=lambda pair: pair[1])
    return (f"{len(smaller)} of {len(panels)} panel(s) are bigger than the {config.width}x"
            f"{config.height} video and are shown smaller than they are - {worst_panel.stem} at "
            f"{worst * 100:.0f}% of its size. {_big_enough(config, 1 / worst)} would show every panel "
            f"at full detail (Settings - Video size); a bigger video takes longer to render.")
