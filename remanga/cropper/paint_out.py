"""What a structured crop may show - the paint-out rule, as box arithmetic on
one page (see remanga.cropper.structured for what a structured crop is).

A structured crop is its frames plus the text and art of its own that reach
past them, cut as the rectangle around all of those. That rectangle routinely
takes in a slice of a neighbour: the bottom of the panel above, because a
bubble hangs down over it, or half a panel, for a group shaped like an L. So,
inside the rectangle, paper colour goes over

    other crops' frames, where they lie outside this crop's own frames,
    and other crops' text_outside, wherever it falls,

except over this crop's own text_outside and art_outside, which always stay.

Two consequences worth knowing. An inset drawn over this crop's own frame
stays, because it is inside a frame this crop shows. And another crop's art
drawn over this crop's frame - a head rising into the tier above - stays too:
only text is ever removed from a frame it covers, because a bubble belongs to
one moment while art inside a frame is part of that frame's picture."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

PixelBox = tuple[int, int, int, int]  # left, top, right, bottom


def bounding_box(boxes: Sequence[PixelBox]) -> PixelBox:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _region(rect: PixelBox, boxes: Sequence[PixelBox]) -> np.ndarray:
    """Which pixels of `rect` fall inside any of `boxes`."""
    left, top, right, bottom = rect
    covered = np.zeros((bottom - top, right - left), dtype=bool)
    for b_left, b_top, b_right, b_bottom in boxes:
        x0, y0 = max(b_left, left) - left, max(b_top, top) - top
        x1, y1 = min(b_right, right) - left, min(b_bottom, bottom) - top
        if x1 > x0 and y1 > y0:
            covered[y0:y1, x0:x1] = True
    return covered


def foreign_mask(
    rect: PixelBox,
    own_frames: Sequence[PixelBox],
    own_kept: Sequence[PixelBox],
    other_frames: Sequence[PixelBox],
    other_text: Sequence[PixelBox],
) -> np.ndarray | None:
    """A (height, width) boolean array over `rect`, True where the crop
    shows something that belongs to another crop - or None when there is
    nothing to paint, which is most crops."""
    paint = (_region(rect, other_frames) & ~_region(rect, own_frames)) | _region(rect, other_text)
    paint &= ~_region(rect, own_kept)
    return paint if paint.any() else None
