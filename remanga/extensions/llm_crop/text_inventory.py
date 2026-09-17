"""A page's text inventory turned into `text_outside`.

Gemini lists every bubble, caption and sound effect on a page with the crop
it belongs to (`"text": [{"crop": 2, "box": [...]}]` - see
prompts/llm_crop.md). Which crop each piece is SHOWN in, and which pieces
have to be in `text_outside`, is decided here (remanga.cropper.paint_out
paints other crops' text_outside out of every rectangle):

- A piece drawn inside one crop's frames (at least DRAWN_IN of its box) is
  shown in that crop, whoever Gemini says it belongs to. Gemini attributes by
  speaker; the page places a bubble where the reader meets it. Moving a bubble
  drawn inside panel 6 to its speaker in panel 5 erased it from panel 6 and
  dragged a strip of panel 6 into panel 5 - measured on RebornTwentyYearsLater
  001_006, twice on one page. The narration still reports who says it.
- A piece not drawn inside any one crop - a caption across a gutter, a bubble
  over a border - goes to the crop Gemini names, so it is shown whole there.
- Either way it is added to that crop's `text_outside` when it reaches past
  the crop's frames or overlaps another crop's frame, so the crop's rectangle
  takes all of it and the neighbour's paints it out. Its box is padded by
  PAD, because a model's box hugs the lettering and leaves the bubble's
  outline outside (001_006: half a bubble).

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
# The share of a piece's box inside one crop's frames that makes it that
# crop's, where it is drawn.
DRAWN_IN = 0.6
# Grid units added around a piece's box when it goes into text_outside.
PAD = 5


def _inside(inner: list[float], outer: list[float], slack: float = TOLERANCE) -> bool:
    return (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack
            and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack)


def _overlaps(a: list[float], b: list[float], slack: float = TOLERANCE) -> bool:
    return (min(a[2], b[2]) - max(a[0], b[0]) > slack
            and min(a[3], b[3]) - max(a[1], b[1]) > slack)


def _area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _covered(box: list[float], frames: list[list[float]]) -> float:
    """How much of `box` lies inside `frames` (overlapping frames can count a
    spot twice, so this is capped at 1)."""
    area = _area(box)
    if not area:
        return 0.0
    inside = sum(_area([max(box[0], f[0]), max(box[1], f[1]), min(box[2], f[2]), min(box[3], f[3])]) for f in frames)
    return min(1.0, inside / area)


def _padded(box: list[float]) -> list[int]:
    return [max(0, round(box[0] - PAD)), max(0, round(box[1] - PAD)),
            min(1000, round(box[2] + PAD)), min(1000, round(box[3] + PAD))]


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
        box = item["box"]
        drawn_in = max(out["crops"], key=lambda crop: _covered(box, crop["frames"]))
        shown_in = drawn_in if _covered(box, drawn_in["frames"]) >= DRAWN_IN else crops[item["crop"]]
        listed = shown_in.setdefault("text_outside", [])
        if any(_inside(box, existing) for existing in listed):
            continue
        beyond_own = not any(_inside(box, frame) for frame in shown_in["frames"])
        over_neighbour = any(_overlaps(box, frame) for other in out["crops"] if other is not shown_in
                             for frame in other["frames"])
        if beyond_own or over_neighbour:
            listed.append(_padded(box))
            added += 1
    return out, added
