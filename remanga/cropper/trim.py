"""Final per-panel whitespace trim: removes any leftover blank margin still
present on an already-cropped panel image.

Gutter-snap and seam reconciliation (remanga.cropper.gutter / .seams) already try
to place each crop boundary correctly before the image is ever cut. This is the
last safety net for what they can't fix by construction: a panel with no neighbor
to reconcile against (a single panel on its own page, or an edge bordering the raw
page margin rather than another panel) can still end up with a slice of pure blank
paper baked into the saved image.

Deliberately conservative: it only trims a thin band of near-pure background off
an edge and stops the instant a row/column no longer qualifies, so it cleans up
genuine leftover slack without eating into the margin_padding_pixels cushion that
exists specifically to protect speech bubbles and bleed art.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from PIL import Image

# (left, top, right, bottom) in the image's own local pixel space.
LocalBox = Tuple[int, int, int, int]


def trim_panel_margins(
    img: Image.Image,
    bg: float,
    tolerance: float = 20.0,
    min_bg_fraction: float = 0.985,
    max_trim_fraction: float = 0.04,
) -> Tuple[Image.Image, LocalBox]:
    """Trims a thin band of near-pure background gray off each of the four edges
    of an already-cropped panel image, stopping the instant a row/column no
    longer qualifies as background. Returns the (possibly) trimmed image plus the
    local box that was applied, so a caller tracking this panel's absolute
    position on the source page can keep that provenance accurate.

    `bg` is the page's sampled background gray level (the same value gutter-snap
    uses for that page), not re-derived from the panel itself - a panel can
    legitimately be almost entirely blank near one edge (a silent reaction beat,
    a sparse splash panel), and trimming from its own content would risk eating
    into that art instead of just the excess gutter.
    """
    w, h = img.size
    if w < 4 or h < 4:
        return img, (0, 0, w, h)

    gray = np.asarray(img.convert("L"), dtype=np.float32)
    max_trim_x = max(0, int(w * max_trim_fraction))
    max_trim_y = max(0, int(h * max_trim_fraction))

    def is_bg_row(y: int) -> bool:
        return float(np.mean(np.abs(gray[y, :] - bg) <= tolerance)) >= min_bg_fraction

    def is_bg_col(x: int) -> bool:
        return float(np.mean(np.abs(gray[:, x] - bg) <= tolerance)) >= min_bg_fraction

    top = 0
    while top < max_trim_y and top < h - 1 and is_bg_row(top):
        top += 1

    bottom = h
    while (h - bottom) < max_trim_y and bottom > top + 1 and is_bg_row(bottom - 1):
        bottom -= 1

    left = 0
    while left < max_trim_x and left < w - 1 and is_bg_col(left):
        left += 1

    right = w
    while (w - right) < max_trim_x and right > left + 1 and is_bg_col(right - 1):
        right -= 1

    local_box = (left, top, right, bottom)
    if local_box == (0, 0, w, h):
        return img, local_box

    return img.crop(local_box), local_box
