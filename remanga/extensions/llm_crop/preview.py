"""Preview images for imported LLM crops, so a chapter's crops can be checked
by eye before anything is cut.

Each preview is two halves side by side:

- **The page**, with Gemini's boxes as imported (before gutter-snap - what
  Gemini said, which is what there is to judge): frames green, text_outside
  blue, art_outside magenta, and the rectangle each crop covers red with its
  order number.
- **The crops themselves**, cut by the very function `crop` uses
  (remanga.cropper.crop_page.cut_crops): gutter-snapped, padded, neighbours
  painted out in paper colour, margins trimmed - each labelled with the same
  order number.

The crops half is there because the page half can't show paint-out
honestly. Every crop paints its own neighbours out of its own rectangle, and
the rectangles overlap, so one tint over the shared page made a crop look as
if its own dialogue were being erased, when the paint belonged to the
neighbour whose rectangle reaches over it. The cut crops show exactly what
each one keeps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from remanga.config import CropperConfig
from remanga.console import console, display_path
from remanga.cropper.crop_page import CutCrop, cut_crops
from remanga.cropper.dedupe import dedupe_panels
from remanga.cropper.structured import plan_structured_crops
from remanga.extensions.llm_crop.bundles import ChapterPage
from remanga.extensions.llm_crop.paths import get_llm_crop_dir

PREVIEW_LONG_SIDE = 1400
FRAME_COLOR = (0, 190, 0)
TEXT_COLOR = (0, 90, 255)
ART_COLOR = (220, 0, 220)
RECT_COLOR = (230, 0, 0)
SHEET_COLOR = (70, 70, 70)
GAP = 12


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int) -> None:
    draw.text(xy, text, font=_font(size), fill=RECT_COLOR, stroke_width=3, stroke_fill=(255, 255, 255))


def _page_half(img: Image.Image, panels: list[dict[str, Any]], cropper: CropperConfig) -> Image.Image:
    """The page scaled to PREVIEW_LONG_SIDE, with every crop's boxes drawn."""
    scale = min(1.0, PREVIEW_LONG_SIDE / max(img.size))
    page = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS) \
        if scale < 1 else img.copy()
    width, height = page.size
    plans = plan_structured_crops(panels, width, height, None, None, cropper)
    draw = ImageDraw.Draw(page)
    line = max(2, round(max(width, height) / 500))
    for panel, plan in zip(panels, plans, strict=False):
        for boxes, color in ((plan.frames, FRAME_COLOR), (plan.text, TEXT_COLOR), (plan.art, ART_COLOR)):
            for box in boxes:
                draw.rectangle(box, outline=color, width=line)
        left, top, right, bottom = plan.rect
        draw.rectangle((left, top, right, bottom), outline=RECT_COLOR, width=line + 1)
        label = f"{panel.get('panel_id')}{' group' if panel.get('kind') == 'group' else ''}"
        _label(draw, (left + 6, top + 4), label, max(16, round(max(width, height) / 45)))
    return page


def _layout(sizes: list[tuple[int, int]], width: int, height: int) -> tuple[int, list[list[int]]]:
    """The tallest row height at which the crops, in order, fill rows of
    `width` without the rows going past `height` - and which crops go in
    each row. Falls back to the smallest height tried."""
    rows: list[list[int]] = []
    row_height = 16
    for row_height in range(min(height, 900), 15, -8):
        rows, x = [[]], 0
        for index, (w, h) in enumerate(sizes):
            scaled = min(width, max(1, round(w * row_height / h)))
            if rows[-1] and x + scaled > width:
                rows.append([])
                x = 0
            rows[-1].append(index)
            x += scaled + GAP
        if len(rows) * (row_height + GAP) <= height:
            break
    return row_height, rows


def _crops_half(cuts: list[CutCrop], labels: list[str], height: int) -> Image.Image:
    """The cut crops in order, as large as fits a PREVIEW_LONG_SIDE-wide
    sheet as tall as the page half."""
    width = PREVIEW_LONG_SIDE
    sheet = Image.new("RGB", (width, height), SHEET_COLOR)
    if not cuts:
        return sheet
    row_height, rows = _layout([cut.image.size for cut in cuts], width - 2 * GAP, height - GAP)
    draw = ImageDraw.Draw(sheet)
    y = GAP
    for row in rows:
        x = GAP
        for index in row:
            image = cuts[index].image
            scale = row_height / image.height
            if image.width * scale > width - 2 * GAP:
                scale = (width - 2 * GAP) / image.width
            shown = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                                 Image.Resampling.LANCZOS)
            sheet.paste(shown, (x, y))
            _label(draw, (x + 4, y + 2), labels[index], max(14, min(28, row_height // 6)))
            x += shown.width + GAP
        y += row_height + GAP
    return sheet


def write_previews(cropper: CropperConfig, project_name: str, chapter_num: str,
                   crops: dict[str, Any], pages: list[ChapterPage]) -> Path:
    """One JPEG per story page into llm_crop/chapter_N/preview/, replacing
    the previous import's."""
    out_dir = get_llm_crop_dir(project_name, chapter_num) / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()

    by_filename = {page.path.name: page for page in pages}
    written = 0
    for entry in crops["pages"]:
        page = by_filename.get(entry["page_filename"])
        if not entry["is_story_page"] or page is None:
            continue
        panels = entry["panels"]
        if cropper.dedupe_duplicate_panels:
            panels, _ = dedupe_panels(panels, iou_threshold=cropper.duplicate_iou_threshold)
        with Image.open(page.path) as src:
            img = ImageOps.exif_transpose(src).convert("RGB")

        page_half = _page_half(img, panels, cropper)
        cuts = cut_crops(img, panels, cropper)
        crops_half = _crops_half(cuts, [str(panel.get("panel_id")) for panel in panels], page_half.height)

        preview = Image.new("RGB", (page_half.width + GAP + crops_half.width, page_half.height), SHEET_COLOR)
        preview.paste(page_half, (0, 0))
        preview.paste(crops_half, (page_half.width + GAP, 0))
        preview.save(out_dir / f"{page.stem}.jpg", quality=88)
        written += 1

    console.print(f"[dim]Previews of {written} page(s), each crop drawn on its page and shown as it will be "
                  f"cut: {display_path(out_dir)}[/]")
    return out_dir
