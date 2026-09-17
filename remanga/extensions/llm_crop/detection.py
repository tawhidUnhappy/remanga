"""Panel detection for the grid upload: MAGI v3 finds each page's panels, and
they are drawn on the grid images as labeled outlines (P1, P2, ... in reading
order) and listed in chapter_info.json, so Gemini names a frame by its label
instead of measuring it.

Why: measured on RebornTwentyYearsLater chapter 1, Gemini decides crops well
- what belongs together, the order, who says what - but places borders badly:
frames started at the page margin where the art bleeds to the edge, a whole
panel came back as a thin strip, two panels as one frame. MAGI's borders on
the same pages were nearly exact. It does merge or miss a panel now and then
(a borderless figure, two panels sharing a scene), which is why a frame can
still be measured by hand when no label fits.

Boxes are stored and shown in square (grid) units, `[ymin, xmin, ymax,
xmax]`, the same units as the rest of the reply. The result is cached beside
the previews and reused while the chapter's pages are unchanged, since a MAGI
pass loads a model onto the GPU (about a minute for 40 pages)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.config import MarkerConfig
from remanga.console import console
from remanga.extensions.llm_crop.paths import get_llm_crop_dir
from remanga.json_io import read_json_or, write_json

CACHE_NAME = "detected_panels.json"


def label(index: int) -> str:
    return f"P{index}"


def _source_key(path: Path) -> list[Any]:
    stat = path.stat()
    return [path.name, stat.st_size, int(stat.st_mtime)]


def _to_square(box: list[float], width: int, height: int) -> list[int]:
    """A MAGI pixel box `[x1, y1, x2, y2]` on a page as `[ymin, xmin, ymax,
    xmax]` on its grid square, where the page's longer side is 1000."""
    scale = 1000 / max(width, height, 1)
    x1, y1, x2, y2 = box
    return [round(y1 * scale), round(x1 * scale), round(y2 * scale), round(x2 * scale)]


def _in_reading_order(boxes: list[list[int]], direction: str) -> list[list[int]]:
    from remanga.webui.mark_ops import reading_order

    marks = [{"id": str(i), "x": b[1], "y": b[0], "w": b[3] - b[1], "h": b[2] - b[0]} for i, b in enumerate(boxes)]
    return [boxes[int(mark["id"])] for mark in reading_order(marks, direction)]


def _magi_available(marker: MarkerConfig) -> str | None:
    """Why detection can't run here, or None when it can."""
    if not marker.magi_enabled:
        return "MAGI is turned off (marker.magi_enabled)"
    from remanga.venvs import get_tool_python
    from remanga.webui.magi_assist import is_gpu_available

    try:
        get_tool_python("magi")
    except FileNotFoundError:
        return "the MAGI environment isn't installed (run setup-tools)"
    if not is_gpu_available():
        return "MAGI needs a CUDA GPU"
    return None


def detect_chapter_panels(marker: MarkerConfig, project_name: str, chapter_num: str,
                          pages: list[Any], direction: str) -> dict[str, dict[str, list[int]]]:
    """{page stem: {"P1": box, ...}} for every page, labels in reading order.
    Empty when MAGI can't run - the upload is then built without labels and
    Gemini measures every frame, as before."""
    cache_path = get_llm_crop_dir(project_name, chapter_num) / CACHE_NAME
    sources = [_source_key(page.path) for page in pages]
    cached = read_json_or(cache_path, {})
    if isinstance(cached, dict) and cached.get("sources") == sources and cached.get("direction") == direction:
        return cached.get("pages", {})

    reason = _magi_available(marker)
    if reason:
        console.print(f"[yellow]No panel labels on the grid: {reason}.[/] [dim]Gemini will measure every frame.[/]")
        return {}

    from remanga.extensions.llm_crop.grid import oriented_size
    from remanga.webui.magi_assist import detect_panels_for_pages

    console.print(f"[cyan]Detecting panels on {len(pages)} page(s) with MAGI v3, to label them on the grid...[/]")
    try:
        found = detect_panels_for_pages([page.path for page in pages], marker)
    except Exception as error:  # a detection failure must not stop the upload being built
        console.print(f"[yellow]Panel detection failed ({error}) - building the grid without labels.[/]")
        return {}

    result: dict[str, dict[str, list[int]]] = {}
    for page in pages:
        width, height = oriented_size(page.path)
        boxes = [_to_square(box, width, height) for box in found.get(page.path.name, [])]
        boxes = [b for b in boxes if b[2] > b[0] and b[3] > b[1]]
        result[page.stem] = {label(i): box for i, box in enumerate(_in_reading_order(boxes, direction), start=1)}
    write_json(cache_path, {"sources": sources, "direction": direction, "pages": result})
    console.print(f"[green]✓ Labeled {sum(len(v) for v in result.values())} detected panels.[/]")
    return result


def cached_chapter_panels(project_name: str, chapter_num: str) -> dict[str, dict[str, list[int]]]:
    """The labels drawn on this chapter's current grid, as built - what a
    reply's frame labels refer to."""
    cached = read_json_or(get_llm_crop_dir(project_name, chapter_num, create=False) / CACHE_NAME, {})
    return cached.get("pages", {}) if isinstance(cached, dict) else {}


def resolve_frame_labels(doc: Any, detected: dict[str, dict[str, list[int]]]) -> list[str]:
    """Replaces every frame a reply gives as a panel label ("P3") with that
    panel's box, in place. Returns the errors that resolving finds: a label
    used for more than one frame on a page (one panel shown twice, or two
    panels a detector merged given one label). A label that isn't on its
    page is left as it is, for the checker to report."""
    if not isinstance(doc, dict) or not isinstance(doc.get("pages"), list):
        return []
    errors = []
    for entry in doc["pages"]:
        if not isinstance(entry, dict):
            continue
        labels = detected.get(entry.get("page"), {})
        used: dict[str, list[str]] = {}
        for crop in entry.get("crops") or []:
            frames = crop.get("frames") if isinstance(crop, dict) else None
            if not isinstance(frames, list):
                continue
            for i, frame in enumerate(frames):
                name = frame.strip().upper() if isinstance(frame, str) else None
                if name in labels:
                    frames[i] = list(labels[name])
                    used.setdefault(name, []).append(str(crop.get("order")))
        for name, orders in used.items():
            if len(orders) > 1:
                errors.append(f"{entry.get('page')}: {name} is used for {len(orders)} frames (crop(s) "
                              f"{', '.join(orders)}) - a panel belongs to one crop; if that outline merges "
                              f"two panels, measure each of them instead")
    return errors


def _area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def panels_in_no_crop(doc: Any, detected: dict[str, dict[str, list[int]]]) -> list[str]:
    """Warnings for detected panels that no crop shows: a label whose box
    isn't at least half covered by the page's frames (after
    resolve_frame_labels). A panel in no crop is missing from the video - on
    RebornTwentyYearsLater 001_015 Gemini left out two of eight. Warnings, not
    errors, because a detector also outlines things that are not panels."""
    warnings = []
    for entry in doc.get("pages", []) if isinstance(doc, dict) else []:
        if not isinstance(entry, dict) or not entry.get("story"):
            continue
        frames = [f for crop in entry.get("crops") or [] if isinstance(crop, dict)
                  for f in crop.get("frames") or [] if isinstance(f, list) and len(f) == 4]
        missing = []
        for name, box in detected.get(entry.get("page"), {}).items():
            covered = sum(_area([max(box[0], f[0]), max(box[1], f[1]), min(box[2], f[2]), min(box[3], f[3])])
                          for f in frames)
            if _area(box) and covered < 0.5 * _area(box):
                missing.append(name)
        if missing:
            warnings.append(f"{entry['page']}: detected panel(s) {', '.join(missing)} are in no crop - missing from "
                            f"the video unless they aren't really panels")
    return warnings
