"""Composing a chapter's panels into video frames.

    canvas.py   one panel on one frame: background, fit, scale
    quality.py  whether this video size shrinks any panel
    frames.py   the frames on disk, built once and reused

Kept as the name the rest of the pipeline imports (video/render.py), so which
file holds what stays an implementation detail."""

from remanga.video.canvas import FrameCompositor
from remanga.video.frames import FRAMES_SETTINGS_NAME, FrameCache
from remanga.video.quality import KEEPS_DETAIL_SCALE, VIDEO_SIZES, downscaled_panels, quality_warning

__all__ = [
    "FRAMES_SETTINGS_NAME",
    "KEEPS_DETAIL_SCALE",
    "VIDEO_SIZES",
    "FrameCache",
    "FrameCompositor",
    "downscaled_panels",
    "quality_warning",
]
