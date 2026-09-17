"""A page's text inventory turned into `text_outside`.

Gemini lists every bubble, caption and sound effect on a page with the crop
it belongs to (`"text": [{"crop": 2, "box": [...]}]` - see
prompts/llm_crop.md). Which of those have to be in their crop's
`text_outside` is then decided here, by the same rule the prompt used to ask
the model to apply itself (remanga.cropper.paint_out):

- a piece that reaches past its owner's frames, so the crop's rectangle
  grows to show it whole - a caption across a gutter, a bubble over a
  border;
- a piece that overlaps another crop's frame, even inside its owner's own
  frame, so it is painted out of that neighbour - the overlap beside a
  slanted border.

Measured on RebornTwentyYearsLater chapter 1: Gemini attributed a place
caption across the gutter between two panels correctly in its reading, but
left it out of both crops' `text_outside`, so each crop showed half of it.

Anything a reply already lists in `text_outside` is kept, and a piece that
one of those boxes already covers isn't added twice. Boxes stay in square
(grid) units; the importer converts them to the page afterwards."""

from __future__ import annotations

import copy
from typing import Any

# How far, in grid units, a piece may poke past a frame (or into a
# neighbour's) and still count as inside - measuring noise, not a real
# overhang. A bubble outline drawn over its own border is typically 1-2.
TOLERANCE = 3


def _inside(inner: list[float], outer: list[float], slack: float = TOLERANCE) -> bool:
    return (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack
            and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack)


def _overlaps(a: list[float], b: list[float], slack: float = TOLERANCE) -> bool:
    return (min(a[2], b[2]) - max(a[0], b[0]) > slack
            and min(a[3], b[3]) - max(a[1], b[1]) > slack)


def text_outside_from_inventory(entry: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """A copy of one checked page entry with its `text` inventory folded into
    its crops' `text_outside`, and how many boxes that added. An entry with
    no inventory comes back unchanged."""
    text = entry.get("text")
    if not entry.get("story") or not text:
        return entry, 0
    out = copy.deepcopy(entry)
    crops = {crop["order"]: crop for crop in out["crops"]}
    added = 0
    for item in text:
        owner = crops[item["crop"]]
        box = item["box"]
        listed = owner.setdefault("text_outside", [])
        if any(_inside(box, existing) for existing in listed):
            continue
        beyond_own = not any(_inside(box, frame) for frame in owner["frames"])
        over_neighbour = any(_overlaps(box, frame) for other in out["crops"] if other is not owner
                             for frame in other["frames"])
        if beyond_own or over_neighbour:
            listed.append(list(box))
            added += 1
    return out, added
