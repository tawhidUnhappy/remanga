"""crops.json for a long strip, written from its strip/ pages' marks.

Pixel boxes, and every page flagged `exact`: the Strip Marker's edges are
placed by hand and may overlap, so the cropper cuts them as they are - no
gutter snapping (it would pull overlapping edges apart), no trimming, no
padding (see remanga/cropper/crop_page.py)."""

from __future__ import annotations

from pathlib import Path

from remanga.json_io import write_json

# The marker's own crops.json format number (webui/marks_file.py:MARKS_FORMAT).
MARKS_FORMAT = 2


def page_boxes(page: dict) -> list[list[float]]:
    """A strip.json page's marks as [x1, y1, x2, y2] pixel boxes."""
    width = page["width"]
    return [[round(left * width), top, round(right * width), bottom]
            for top, bottom, left, right in page.get("panels", [])]


def write_crops(crops_path: Path, chapter: str, pages: list[dict]) -> None:
    entries = []
    for index, page in enumerate(pages, start=1):
        boxes = page_boxes(page)
        entries.append({
            "page_index": index,
            "page_filename": page["file"],
            "is_story_page": bool(boxes),
            "exact": True,
            "panels": [{"panel_id": i, "box_pixel": [y1, x1, y2, x2], "src": "manual"}
                       for i, (x1, y1, x2, y2) in enumerate(boxes, start=1)],
        })
    write_json(crops_path, {"chapter": str(chapter), "marks_format": MARKS_FORMAT, "pages": entries})
