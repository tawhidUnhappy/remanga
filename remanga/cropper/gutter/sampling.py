"""Reading a page as numbers: grayscale conversion and what its background
(paper) color actually is.

Both answers are computed once per page and threaded through every panel's
refinement, which is why they live apart from the refinement itself - a
per-page cost that must not become a per-panel one."""

from __future__ import annotations

from typing import Tuple

import numpy as np
from PIL import Image

# (left, top, right, bottom) - Pillow crop-box order. Defined here, with the
# page-level primitives, because it's the vocabulary every other module in
# this package speaks in.
PixelBox = Tuple[int, int, int, int]


def page_grayscale_array(img: Image.Image) -> np.ndarray:
    """Converts a page image to a float32 grayscale array for gutter scoring."""
    return np.asarray(img.convert("L"), dtype=np.float32)


def sample_background_color(gray: np.ndarray, strip: int = 12) -> float:
    """Estimates the page's paper/background gray level from its outer margins,
    which are guaranteed to never fall inside a panel, so they're a safe reference
    for "what blank page/gutter looks like" on this particular scan."""
    h, w = gray.shape
    strip = max(1, min(strip, h // 4 or 1, w // 4 or 1))
    edges = np.concatenate([
        gray[:strip, :].ravel(),
        gray[-strip:, :].ravel(),
        gray[:, :strip].ravel(),
        gray[:, -strip:].ravel(),
    ])
    return float(np.median(edges))


