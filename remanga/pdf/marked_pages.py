"""Every page of a chapter with its panel marks drawn on it - what the LLM
gets beside the cut panels, so it can see the page a panel came from.

A cut panel on its own says nothing about where it sat: which panels share a
tier, which one a character is looking across at, what a splash page is doing
under three insets. The reader of a manga takes all of that from the page.
So the PDF now carries both, and these are the page images it carries (user
request, 2026-09-22): the page as it was downloaded, with each panel's box
outlined and labelled with the panel's own id - the same marks, in the same
colour, as the Panel Marker shows in the browser.

Never a raw page: a page without its boxes would leave the LLM to guess which
crop is which, which is exactly the guess the ids exist to remove.

The images are written beside the PDF they go into (projects/P/pdf/chapter_N/
pages/), so they are rebuilt with it, thrown away with it, and can be looked
at when a panel comes out wrong.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from remanga.cropper.geometry import calculate_pixel_bounds
from remanga.cropper.naming import page_stem, panel_stem
from remanga.cropper.page_locator import locate_page_file

# The Panel Marker's own mark colours (webui/static_shared/css/theme.css:
# --accent, --accent-ink), so the page in the PDF looks like the page in the
# browser the marks were drawn in. The browser also tints a mark's inside;
# that is left off here - a wash over every panel is a wash over the art and
# the lettering the LLM has to read.
MARK_COLOR = (254, 166, 43)
LABEL_INK = (26, 18, 6)

# All three scale with the page, so a 900px scan and a 3000px one come out
# looking the same: the box outline, the label's type, and the padding
# around it.
_OUTLINE_DIVISOR = 350
_LABEL_DIVISOR = 60

_WORKERS = min(8, os.cpu_count() or 1)


@dataclass
class MarkedPage:
    """One page of the chapter, drawn: where the image is, what it is called
    (`001_003` - the same name the panels cut from it carry), and those
    panels' ids in reading order. A page nobody marked has none, and goes in
    anyway - the chapter reads as a chapter, and a page left out is a hole
    the LLM cannot see."""

    stem: str
    path: Path
    panel_stems: list[str] = field(default_factory=list)


def _label_font(size: int) -> ImageFont.FreeTypeFont:
    """Pillow's own scalable default - no font file to find, no system font
    to depend on (Pillow >= 10.1; every supported version here has it)."""
    return ImageFont.load_default(size=size)


def _draw_marks(img: Image.Image, boxes: list[tuple[tuple[int, int, int, int], str]]) -> None:
    """Outlines each box and labels it with its panel id, in place.

    The label sits INSIDE its own box, in the top-left corner, rather than
    above it as the browser draws it. On screen a mark has the whole canvas
    around it; here the page is the whole image, and a label hung above a box
    lands on top of whatever panel is above it - so a page's last panel would
    stamp its id across the panel before it. Inside, a label can only ever
    cover its own panel, which is also the one panel the LLM has a clean,
    unmarked copy of: the cut image a few pages later."""
    draw = ImageDraw.Draw(img)
    width, height = img.size
    short = min(width, height)
    outline = max(2, round(short / _OUTLINE_DIVISOR))
    font = _label_font(max(12, round(short / _LABEL_DIVISOR)))
    pad = max(2, outline)

    for (left, top, right, bottom), label in boxes:
        draw.rectangle((left, top, right - 1, bottom - 1), outline=MARK_COLOR, width=outline)
        tl, tt, tr, tb = draw.textbbox((0, 0), label, font=font)
        box_w, box_h = tr - tl + 2 * pad, tb - tt + 2 * pad
        # Kept on the page even where the panel runs to its edge; a label
        # wider than its own panel (a sliver of a panel) still starts at that
        # panel's corner, so it is never in doubt which box it names.
        x = min(max(0, left + outline), max(0, width - box_w))
        y = min(max(0, top + outline), max(0, height - box_h))
        draw.rectangle((x, y, x + box_w, y + box_h), fill=MARK_COLOR)
        draw.text((x + pad - tl, y + pad - tt), label, font=font, fill=LABEL_INK)


def _save_beside_source(img: Image.Image, source: Path, out_path: Path) -> None:
    """Writes the drawn page in the format its source page is in.

    A JPEG page saved as JPEG goes into the PDF as its own bytes
    (pdf/encode.py:_jpeg_passthrough) - re-encoding a scan's pixels into a
    lossless PNG is several times the size for a picture that is already
    lossy. Anything else is saved lossless, as it was."""
    if source.suffix.lower() in (".jpg", ".jpeg"):
        img.save(out_path, "JPEG", quality=95, subsampling=0, optimize=True)
    else:
        img.save(out_path, "PNG", optimize=True)


def _page_boxes(page_entry: dict[str, Any], chapter_num, page_number: int,
                size: tuple[int, int]) -> list[tuple[tuple[int, int, int, int], str]]:
    """This page's marks as pixel boxes with their panel ids - the marks as
    drawn, not as cut: the boxes here are the ones the marker shows, and the
    cropper's own padding and gutter-snapping are its business.

    Panel ids are built the way the cropper builds them
    (cropper/naming.panel_stem, off `page_index` and a per-page count from 1),
    so a label on a page and the file name of the panel cut from it cannot
    drift apart."""
    width, height = size
    boxes = []
    for index, panel in enumerate(page_entry.get("panels") or [], start=1):
        box = panel.get("box_1000") or panel.get("box_pixel") or panel.get("coordinates")
        if not box or len(box) != 4:
            continue
        is_normalized = "box_1000" in panel or max(box) <= 1000
        bounds = calculate_pixel_bounds(box, width, height, is_1000=is_normalized)
        boxes.append((bounds, panel_stem(chapter_num, page_number, index)))
    return boxes


def build_marked_pages(crops: dict[str, Any], pages_dir: Path, out_dir: Path, chapter_num) -> list[MarkedPage]:
    """Draws every page of the chapter into `out_dir` and returns them in
    reading order. `crops` is the chapter's crops.json as read.

    `out_dir` is emptied first: a page that has since been removed from the
    chapter must not linger there and end up in the next PDF."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.iterdir():
        if stale.is_file():
            stale.unlink()

    jobs = []
    for position, page_entry in enumerate(crops.get("pages") or [], start=1):
        page_number = page_entry.get("page_index") or position
        source = locate_page_file(pages_dir, page_entry.get("page_filename"), page_entry.get("page_index"),
                                  chapter_num)
        if source is None or not source.exists():
            continue
        jobs.append((page_entry, page_number, source))

    def draw_one(job: tuple[dict[str, Any], int, Path]) -> MarkedPage:
        page_entry, page_number, source = job
        with Image.open(source) as opened:
            img = ImageOps.exif_transpose(opened).convert("RGB")
        boxes = _page_boxes(page_entry, chapter_num, page_number, img.size)
        _draw_marks(img, boxes)
        stem = page_stem(chapter_num, page_number)
        out_path = out_dir / f"{stem}{source.suffix.lower()}"
        _save_beside_source(img, source, out_path)
        return MarkedPage(stem, out_path, [label for _box, label in boxes])

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        return list(pool.map(draw_one, jobs))
