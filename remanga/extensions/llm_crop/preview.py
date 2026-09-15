"""Preview images for imported LLM crops: every crop drawn on its page, so a
chapter's crops can be checked by eye before anything is cut.

Drawn from the boxes as imported, before gutter-snap - what Gemini said, which
is what there is to judge. Frames are green, text_outside blue, art_outside
magenta, the rectangle that will be cut red with its order number, and
whatever the cut will paint over is tinted red."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from remanga.config import CropperConfig
from remanga.console import console, display_path
from remanga.cropper.structured import paint_mask, plan_structured_crops
from remanga.extensions.llm_crop.bundles import ChapterPage
from remanga.extensions.llm_crop.paths import get_llm_crop_dir

PREVIEW_LONG_SIDE = 1400
FRAME_COLOR = (0, 190, 0)
TEXT_COLOR = (0, 90, 255)
ART_COLOR = (220, 0, 220)
RECT_COLOR = (230, 0, 0)
PAINT_TINT = np.array([255, 60, 60])


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
        with Image.open(page.path) as src:
            img = ImageOps.exif_transpose(src).convert("RGB")
        scale = PREVIEW_LONG_SIDE / max(img.size)
        if scale < 1:
            img = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
        width, height = img.size

        plans = plan_structured_crops(entry["panels"], width, height, None, None, cropper)
        if cropper.paint_out:
            tint = np.zeros((height, width), dtype=bool)
            for index, plan in enumerate(plans):
                left, top, right, bottom = plan.rect
                paint = paint_mask(plans, index, plan.rect)
                if paint is not None:
                    tint[top:bottom, left:right] |= paint
            if tint.any():
                pixels = np.array(img)
                pixels[tint] = (pixels[tint] * 0.45 + PAINT_TINT * 0.55).astype(np.uint8)
                img = Image.fromarray(pixels)

        draw = ImageDraw.Draw(img)
        line = max(2, round(max(width, height) / 500))
        font = ImageFont.load_default(size=max(16, round(max(width, height) / 45)))
        for panel, plan in zip(entry["panels"], plans, strict=False):
            for boxes, color in ((plan.frames, FRAME_COLOR), (plan.text, TEXT_COLOR), (plan.art, ART_COLOR)):
                for box in boxes:
                    draw.rectangle(box, outline=color, width=line)
            left, top, right, bottom = plan.rect
            draw.rectangle((left, top, right, bottom), outline=RECT_COLOR, width=line + 1)
            label = f"{panel.get('panel_id')}{' group' if panel.get('kind') == 'group' else ''}"
            draw.text((left + 6, top + 4), label, font=font, fill=RECT_COLOR,
                      stroke_width=3, stroke_fill=(255, 255, 255))
        img.save(out_dir / f"{page.stem}.jpg", quality=88)
        written += 1

    console.print(f"[dim]Previews of {written} page(s): {display_path(out_dir)}[/]")
    return out_dir
