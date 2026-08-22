"""Pure panel-box coordinate math: normalized-to-pixel conversion and margin padding."""

from __future__ import annotations

from typing import List, Tuple


def calculate_pixel_bounds(box: List[int], img_w: int, img_h: int, is_1000: bool) -> Tuple[int, int, int, int]:
    """Converts [ymin, xmin, ymax, xmax] into a Pillow crop box (left, upper, right, lower)."""
    ymin, xmin, ymax, xmax = box

    if is_1000:
        left = int((xmin / 1000.0) * img_w)
        top = int((ymin / 1000.0) * img_h)
        right = int((xmax / 1000.0) * img_w)
        bottom = int((ymax / 1000.0) * img_h)
    else:
        left = int(xmin)
        top = int(ymin)
        right = int(xmax)
        bottom = int(ymax)

    left = max(0, min(left, img_w - 1))
    top = max(0, min(top, img_h - 1))
    right = max(left + 1, min(right, img_w))
    bottom = max(top + 1, min(bottom, img_h))

    return (left, top, right, bottom)


def pixel_bounds_to_box_1000(bounds: Tuple[int, int, int, int], img_w: int, img_h: int) -> List[int]:
    """Inverse of calculate_pixel_bounds: converts a Pillow crop box (left, upper,
    right, lower) in pixel space back into normalized [ymin, xmin, ymax, xmax] on
    the 0-1000 scale crops.json uses. Used by the panel-marking web UI to save
    marks drawn in pixel space in the same schema the LLM crop stage produced."""
    left, top, right, bottom = bounds
    img_w = max(1, img_w)
    img_h = max(1, img_h)
    ymin = round((top / img_h) * 1000)
    xmin = round((left / img_w) * 1000)
    ymax = round((bottom / img_h) * 1000)
    xmax = round((right / img_w) * 1000)
    return [
        max(0, min(999, ymin)),
        max(0, min(999, xmin)),
        max(1, min(1000, ymax)),
        max(1, min(1000, xmax)),
    ]


def apply_padding(bounds: Tuple[int, int, int, int], img_w: int, img_h: int, padding: int) -> Tuple[int, int, int, int]:
    """Expands bounds by padding pixels while preserving image bounds."""
    left, top, right, bottom = bounds
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(img_w, right + padding),
        min(img_h, bottom + padding)
    )
