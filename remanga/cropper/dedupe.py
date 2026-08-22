"""Duplicate/overlapping panel-crop detection — a code-level safety net behind the
crop prompt's Rule 8 ("One Physical Frame, One Crop — No Duplicate or Overlapping
Panels").

Manga legitimately draws the same character across several separately bordered
panels in a row (a close-up, then a wider reaction shot, then another close-up) —
that's completely normal and each one gets its own crop. What this module catches
is a *different* failure: the LLM emitting two `panels` entries on the same page
whose boxes describe the same bordered frame (or near-identical regions of the
page) — which would crop that one frame twice into two separate panel images and
then narrate it twice downstream.

Pure Python — operates directly on the normalized `box_1000` coordinates from
crops.json, before any pixel conversion, so it works regardless of image size.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

Box = Sequence[float]  # [ymin, xmin, ymax, xmax]


def _extract_box(panel: Dict[str, Any]) -> Optional[List[float]]:
    box = panel.get("box_1000") or panel.get("box_pixel") or panel.get("coordinates")
    if not box or len(box) != 4:
        return None
    return [float(v) for v in box]


def _box_area(box: Box) -> float:
    ymin, xmin, ymax, xmax = box
    return max(0.0, ymax - ymin) * max(0.0, xmax - xmin)


def _intersection_area(a: Box, b: Box) -> float:
    ay0, ax0, ay1, ax1 = a
    by0, bx0, by1, bx1 = b
    inter_y0, inter_x0 = max(ay0, by0), max(ax0, bx0)
    inter_y1, inter_x1 = min(ay1, by1), min(ax1, bx1)
    return max(0.0, inter_y1 - inter_y0) * max(0.0, inter_x1 - inter_x0)


def intersection_over_union(a: Box, b: Box) -> float:
    """Standard IoU between two [ymin, xmin, ymax, xmax] boxes."""
    inter = _intersection_area(a, b)
    if inter <= 0:
        return 0.0
    union = _box_area(a) + _box_area(b) - inter
    return inter / union if union > 0 else 0.0


def smaller_box_containment(a: Box, b: Box) -> float:
    """What fraction of the *smaller* box's area the intersection covers. Catches
    the case where one box sits almost entirely inside a much larger one (a
    near-duplicate at a different scale) — plain IoU under-weights this because a
    big/small area mismatch tanks the union-based ratio even when the smaller box
    is basically wholly re-cropping part of the bigger one."""
    inter = _intersection_area(a, b)
    if inter <= 0:
        return 0.0
    smaller = min(_box_area(a), _box_area(b))
    return inter / smaller if smaller > 0 else 0.0


def find_duplicate_pairs(
    panels: List[Dict[str, Any]],
    iou_threshold: float = 0.6,
    containment_threshold: float = 0.85,
) -> List[Tuple[int, int, float, float]]:
    """Returns (earlier_index, later_index, iou, containment) for every pair of
    panels on a page whose boxes are duplicates/near-duplicates by either measure.
    Indices are positions in the given `panels` list (reading order per Rule 6)."""
    boxes = [_extract_box(p) for p in panels]
    results: List[Tuple[int, int, float, float]] = []
    for i in range(len(panels)):
        if boxes[i] is None:
            continue
        for j in range(i + 1, len(panels)):
            if boxes[j] is None:
                continue
            iou = intersection_over_union(boxes[i], boxes[j])
            containment = smaller_box_containment(boxes[i], boxes[j])
            if iou >= iou_threshold or containment >= containment_threshold:
                results.append((i, j, iou, containment))
    return results


def dedupe_panels(
    panels: List[Dict[str, Any]],
    iou_threshold: float = 0.6,
    containment_threshold: float = 0.85,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Drops later duplicate panel entries, keeping the earliest / first-in-
    reading-order occurrence (per Rule 6) as the survivor. Returns
    (kept_panels, dropped_report) where each dropped_report entry describes what
    was removed and why, for logging back to the operator."""
    duplicate_pairs = find_duplicate_pairs(panels, iou_threshold, containment_threshold)

    to_drop: set = set()
    replaced_by: Dict[int, int] = {}

    def resolve(idx: int) -> int:
        while idx in replaced_by:
            idx = replaced_by[idx]
        return idx

    dropped_report: List[Dict[str, Any]] = []
    for i, j, iou, containment in duplicate_pairs:
        if j in to_drop:
            continue
        keeper = resolve(i)
        if keeper == j:
            continue
        to_drop.add(j)
        replaced_by[j] = keeper
        dropped_report.append({
            "kept_index": keeper,
            "dropped_index": j,
            "kept_panel_id": panels[keeper].get("panel_id"),
            "dropped_panel_id": panels[j].get("panel_id"),
            "iou": round(iou, 3),
            "containment": round(containment, 3),
        })

    kept_panels = [p for idx, p in enumerate(panels) if idx not in to_drop]
    return kept_panels, dropped_report
