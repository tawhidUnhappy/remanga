"""What a panel detector saw on a page besides the panels - figures and speech
bubbles - kept beside the pages as chapters/chapter_N/found.json, so the crop
PDF can point at a figure or bubble that crosses a panel border
(breakouts.py). MAGI v3 writes it each time it finds a chapter's panels; a
chapter detected before it did has none until the crop PDF asks for it.

    {"version": 1, "pages": {"001_007.png": {"size": [w, h], "figures": [[x1, y1, x2, y2], ...],
     "texts": [...], "balloons": [...], "essential": [true, ...], "tails": [...],
     "text_tails": [[text, tail], ...]}}}

Boxes are in the page's pixels; a page whose image is no longer that size
(downloaded again, at another quality) is not read. A detector's text box
holds the lettering only, so `balloons` widens each to the speech balloon
around it (balloon_box): a crop that takes in the words but cuts the
balloon's outline looks broken."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from remanga.json_io import read_json_or, write_json
from remanga.paths import get_pages_dir

FOUND_NAME = "found.json"


def found_path(pages_dir: Path) -> Path:
    return pages_dir.parent / FOUND_NAME


def save_found(pages_dir: Path, found: dict[str, dict]) -> None:
    """One detection pass's pages merged into the chapter's record, each text
    box widened to its balloon."""
    if not found:
        return
    for name, page in found.items():
        if page.get("texts") and "balloons" not in page and (pages_dir / name).exists():
            with Image.open(pages_dir / name) as image:
                gray = np.asarray(image.convert("L"))
            page["balloons"] = [balloon_box(gray, box) for box in page["texts"]]
    path = found_path(pages_dir)
    record = read_json_or(path, {}) or {}
    record.setdefault("pages", {}).update(found)
    record["version"] = 1
    write_json(path, record)


DARK = 110       # a balloon's outline is darker than this
_SAMPLES = 5     # rows (columns) scanned across the text, for each side


def balloon_box(gray: np.ndarray, box: list[float]) -> list[float]:
    """The speech balloon around a text box, in pixels: from each side of the
    text, the first dark line past a white gap (letters touching the text box
    are not an outline) - the balloon's border. A side with none near (a
    caption on the art, an open balloon) gets a small margin instead."""
    h, w = gray.shape
    x1, y1, x2, y2 = (round(v) for v in box)
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w - 1, x2), min(h - 1, y2)
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    dark = gray < DARK
    gap = max(3, round(min(bw, bh) * 0.08))

    def outline(line: np.ndarray) -> int | None:
        """How far along `line` the outline is: the first dark pixel after `gap` white ones."""
        white = 0
        for i, is_dark in enumerate(line):
            if not is_dark:
                white += 1
            elif white >= gap:
                return i
            else:
                white = 0
        return None

    def side(lines: list[np.ndarray]) -> int | None:
        found = [d for d in (outline(line) for line in lines) if d is not None]
        return int(np.median(found)) if len(found) * 2 > len(lines) else None

    reach_x, reach_y = max(24, round(bw * 0.8)), max(24, round(bh * 1.8))
    rows = np.linspace(y1 + bh * 0.2, y2 - bh * 0.2, _SAMPLES).round().astype(int)
    cols = np.linspace(x1 + bw * 0.2, x2 - bw * 0.2, _SAMPLES).round().astype(int)
    left = side([dark[y, max(0, x1 - reach_x):x1][::-1] for y in rows])
    right = side([dark[y, x2:min(w, x2 + reach_x)] for y in rows])
    top = side([dark[max(0, y1 - reach_y):y1, x][::-1] for x in cols])
    bottom = side([dark[y2:min(h, y2 + reach_y), x] for x in cols])
    pad_x, pad_y, rim = round(bw * 0.08), round(bh * 0.25), max(2, round(min(w, h) / 400))
    return [float(max(0, x1 - (left + rim if left is not None else pad_x))),
            float(max(0, y1 - (top + rim if top is not None else pad_y))),
            float(min(w, x2 + (right + rim if right is not None else pad_x))),
            float(min(h, y2 + (bottom + rim if bottom is not None else pad_y)))]


def read_found(project: str, chapter: str) -> dict[str, dict]:
    """{page filename: what was found on it}, for the pages still the size
    they were when it was found. A page saved without its balloons gets them
    now."""
    pages_dir = get_pages_dir(project, chapter)
    pages = (read_json_or(found_path(pages_dir), {}) or {}).get("pages") or {}
    kept, widened = {}, {}
    for name, page in pages.items():
        path = pages_dir / name
        if not path.exists():
            continue
        with Image.open(path) as image:
            if list(image.size) != list(page.get("size") or []):
                continue
            if page.get("texts") and "balloons" not in page:
                gray = np.asarray(image.convert("L"))
                page["balloons"] = [balloon_box(gray, box) for box in page["texts"]]
                widened[name] = page
        kept[name] = page
    if widened:
        save_found(pages_dir, widened)
    return kept
