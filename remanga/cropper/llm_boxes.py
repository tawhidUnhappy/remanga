"""Per-page crop planning for LLM crops: turns crops.json entries that carry
`frames` (written by remanga.cropper.llm_reply from Gemini's reply) into the
rectangle to cut for each crop, and what to paint out of it.

Every frame is gutter-snapped exactly the way a marked box is, with every
other frame on the page as the neighbours its search must not cross. What is
not a frame - a bubble hanging past one, hair breaking out of one - is never
snapped: it joins the rectangle afterwards, where Gemini measured it, so a
gutter search can't pull a crop's edge back across the very bubble it reached
that far for.

Seam reconciliation (remanga.cropper.seams) is deliberately NOT run here. It
re-derives the shared edge of two consecutive boxes from one joint gutter
search, which assumes a gutter lies between them - true of marker boxes read
in order, false of Gemini's frames, where a borderless figure's frame starts
exactly where the bordered panel above it ends. Measured on Yandere 002_019:
the search found the gutter ABOVE the "Beep" panel instead and moved its
bottom edge up to it, cutting a 958x82 panel down to a 958x33 sliver - and
the collapsed frame then left the rest of that panel unpainted in the
neighbour's crop. Gemini is told to keep frames of different crops from
overlapping, so there is no double-claimed strip for a seam pass to settle.

A page where no entry has `frames` never gets here: crop_page keeps the
marker's path for it, unchanged."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.cropper.geometry import calculate_pixel_bounds
from remanga.cropper.gutter import PixelBox, refine_box_to_gutters
from remanga.cropper.llm_mask import bounding_box, foreign_mask
from remanga.cropper.panel_boxes import adaptive_gutter_radius


@dataclass
class CropPlan:
    """One crop of a page, in page pixels. `marked` holds its frames as they
    arrived and `frames` the same frames after refinement; `text` and `art`
    are its own text_outside and art_outside. A marker-made panel is a plan
    with one frame and nothing outside it."""

    marked: list[PixelBox]
    frames: list[PixelBox]
    text: list[PixelBox] = field(default_factory=list)
    art: list[PixelBox] = field(default_factory=list)

    @property
    def rect(self) -> PixelBox:
        """The rectangle to cut, before margin padding."""
        return bounding_box(self.frames + self.text + self.art)


def has_llm_crops(panels: Sequence[dict[str, Any]]) -> bool:
    return any(panel.get("frames") for panel in panels)


def _is_box(value: Any) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(isinstance(v, (int, float)) for v in value))


def plan_llm_crops(
    panels: Sequence[dict[str, Any]],
    img_w: int,
    img_h: int,
    gray_arr: np.ndarray | None,
    bg_level: float | None,
    config: CropperConfig,
) -> list[CropPlan]:
    """Every crop on the page, in crops.json order, with snapped frames."""

    def pixels(boxes: Any) -> list[PixelBox]:
        return [calculate_pixel_bounds(list(box), img_w, img_h, is_1000=True)
                for box in boxes or [] if _is_box(box)]

    plans: list[CropPlan] = []
    for panel in panels:
        # An entry without frames on a page that has them is a box drawn or
        # moved in the marker after the import: one frame, nothing outside.
        marked = pixels(panel.get("frames") or [panel.get("box_1000")])
        if not marked:
            console.print(f"[yellow]Skipping a crop with no valid frame: {_esc(str(panel))}[/]")
            continue
        plans.append(CropPlan(
            marked=marked, frames=list(marked),
            text=pixels(panel.get("text_outside")), art=pixels(panel.get("art_outside")),
        ))

    if gray_arr is None or bg_level is None or not config.snap_to_gutters:
        return plans

    radius = adaptive_gutter_radius(config, img_w, img_h)
    flat = [box for plan in plans for box in plan.marked]
    snapped = [
        refine_box_to_gutters(
            gray_arr, box, bg_level,
            other_boxes=flat[:i] + flat[i + 1:],
            search_radius=radius,
            tolerance=config.gutter_bg_tolerance,
            min_run=config.gutter_min_run_pixels,
            min_bg_fraction=config.gutter_min_background_fraction,
        )
        for i, box in enumerate(flat)
    ]

    cursor = 0
    for plan in plans:
        plan.frames = snapped[cursor:cursor + len(plan.marked)]
        cursor += len(plan.marked)
    return plans


def paint_mask(plans: Sequence[CropPlan], index: int, rect: PixelBox) -> np.ndarray | None:
    """What to paint over inside `rect` (the padded rectangle actually cut)
    for plans[index] - see remanga.cropper.llm_mask for the rule."""
    plan = plans[index]
    others = [other for i, other in enumerate(plans) if i != index]
    return foreign_mask(
        rect, plan.frames, plan.text + plan.art,
        [box for other in others for box in other.frames],
        [box for other in others for box in other.text],
    )
