"""Duplicate panel-crop detection — a code-level safety net for crops.json, which
now always comes from a human drawing/adjusting boxes in the Panel Marker web UI
(remanga/webui/), not an LLM transcribing panel coordinates as free text. What
this module catches is an accidental double-mark: two `panels` entries on the
same page whose boxes describe the same bordered frame (or near-identical
regions of the page) — which would crop that one frame twice into two separate
panel images and then narrate it twice downstream.

Manga legitimately draws a small panel nested inside, or heavily overlapping, a
much larger one (an inset reaction shot, a staggered/diagonal layout) — that's a
completely normal, deliberate layout, not a duplicate, and each one gets its own
crop. Only near-identical position AND size (IoU) counts as a duplicate here -
there is deliberately no "smaller box mostly inside a bigger one" containment
check anymore, since that fires on exactly this legitimate nested-panel case and
would silently drop a panel the user explicitly marked (see git history if you're
looking for it - it was removed because of that false-positive).

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


def find_duplicate_pairs(
    panels: List[Dict[str, Any]],
    iou_threshold: float = 0.6,
) -> List[Tuple[int, int, float]]:
    """Returns (earlier_index, later_index, iou) for every pair of panels on a
    page whose boxes are near-identical in both position and size. Indices are
    positions in the given `panels` list (reading order per Rule 6)."""
    boxes = [_extract_box(p) for p in panels]
    results: List[Tuple[int, int, float]] = []
    for i in range(len(panels)):
        if boxes[i] is None:
            continue
        for j in range(i + 1, len(panels)):
            if boxes[j] is None:
                continue
            iou = intersection_over_union(boxes[i], boxes[j])
            if iou >= iou_threshold:
                results.append((i, j, iou))
    return results


def dedupe_panels(
    panels: List[Dict[str, Any]],
    iou_threshold: float = 0.6,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Drops later duplicate panel entries, keeping the earliest / first-in-
    reading-order occurrence (per Rule 6) as the survivor. Returns
    (kept_panels, dropped_report) where each dropped_report entry describes what
    was removed and why, for logging back to the operator."""
    duplicate_pairs = find_duplicate_pairs(panels, iou_threshold)

    to_drop: set = set()
    replaced_by: Dict[int, int] = {}

    def resolve(idx: int) -> int:
        while idx in replaced_by:
            idx = replaced_by[idx]
        return idx

    dropped_report: List[Dict[str, Any]] = []
    for i, j, iou in duplicate_pairs:
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
        })

    kept_panels = [p for idx, p in enumerate(panels) if idx not in to_drop]
    return kept_panels, dropped_report
