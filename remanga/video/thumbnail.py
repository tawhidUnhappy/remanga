"""Recap thumbnails (1280x720) from a chapter's own cut panels or colour
pages: tiles side by side, yellow Anton labels in a black outline, block
arrows aimed at faces. House style from AMV_CD/amv/shorts/thumb.py and
/mnt/datadisk/thumbnail_examples (see .claude/skills/remanga-thumbnails).

A spec (projects/<P>/upload/thumbnail.json, or a key of specs.example.json):

    {"project": "...", "chapter": "1",
     "tiles":  [{"panel": "001_012_01", "w": 0.55, "zoom": 1.25, "cx": 0.5, "cy": 0.35},
                {"page": "001_002.jpg", "box": [530, 60, 1085, 1000], "w": 0.45}],
     "labels": [{"text": "SADIST\\nPRINCESS", "at": [0.15, 0.74], "to": [0.29, 0.38], "size": 84},
                {"text": "CH {num}", "at": [0.08, 0.08], "size": 60}]}

`chapter` is where the tiles come from (a tile's own `chapter` overrides
it), not the chapter the thumbnail is for. tiles: `w` is the tile's share of the width (they add up to 1), `zoom`
crops in, `cx`/`cy` the crop centre as fractions of the panel; `page` (a file
in pages/, e.g. a colour cover) with an optional `box` [l, t, r, b] in page
pixels instead of `panel`. labels: `at` the label centre, `to` the arrow tip
(no `to`: no arrow), both as fractions of the canvas - read them off a grid
render, never guess. A label's text may hold {num} (01, 05.5, 01-02) and
{chapter} (Chapter 1, Chapters 1-2): the one thumbnail of a project, stamped
for each video."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from remanga.paths import REPO_ROOT, get_pages_dir, get_panels_dir

W, H = 1280, 720
YELLOW, BLACK = (255, 230, 0), (8, 8, 8)
FONT = REPO_ROOT / "assets" / "fonts" / "Anton-Regular.ttf"


def _tile(project: str, chapter: str, t: dict, box_w: int) -> Image.Image:
    """The panel (or page) cropped to the tile's shape around (cx, cy), scaled to fill it."""
    if "page" in t:  # a whole page, e.g. a colour cover the cutter never made panels of
        im = Image.open(get_pages_dir(project, chapter) / t["page"]).convert("RGB")
        if "box" in t:
            im = im.crop(tuple(t["box"]))
    else:
        im = Image.open(get_panels_dir(project, chapter, create=False) / f"{t['panel']}.png").convert("RGB")
    zoom, aspect = t.get("zoom", 1.0), box_w / H
    ch = im.height / zoom
    cw = ch * aspect
    if cw > im.width / zoom:  # panel narrower than the tile: fit the width instead
        cw = im.width / zoom
        ch = cw / aspect
    x = min(max(t.get("cx", 0.5) * im.width, cw / 2), im.width - cw / 2)
    y = min(max(t.get("cy", 0.5) * im.height, ch / 2), im.height - ch / 2)
    crop = im.crop((round(x - cw / 2), round(y - ch / 2), round(x + cw / 2), round(y + ch / 2)))
    return crop.resize((box_w, H), Image.LANCZOS)


def _arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], tip: tuple[float, float],
           width: float = 30) -> None:
    """A fat block arrow from start to tip, outlined in black."""
    dx, dy = tip[0] - start[0], tip[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 20:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head_len, head_w = min(length * 0.55, width * 2.1), width * 1.25
    neck = (tip[0] - ux * head_len, tip[1] - uy * head_len)
    half = width / 2
    draw.polygon([(start[0] + px * half, start[1] + py * half), (neck[0] + px * half, neck[1] + py * half),
                  (neck[0] + px * head_w, neck[1] + py * head_w), tip,
                  (neck[0] - px * head_w, neck[1] - py * head_w), (neck[0] - px * half, neck[1] - py * half),
                  (start[0] - px * half, start[1] - py * half)], fill=YELLOW, outline=BLACK, width=6)


def compose(spec: dict, grid: bool = False, fields: dict[str, str] | None = None) -> Image.Image:
    """The thumbnail `spec` describes; `fields` fill the labels' {num} and
    {chapter}. With `grid`, no labels and a 10% grid to read positions off."""
    chapter = str(spec.get("chapter", "1"))
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    x, seams = 0, []
    for k, t in enumerate(spec["tiles"]):
        w = W - x if k == len(spec["tiles"]) - 1 else round(t["w"] * W)
        canvas.paste(_tile(spec["project"], str(t.get("chapter", chapter)), t, w), (x, 0))
        x += w
        seams.append(x)
    for seam in seams[:-1]:  # after every tile is down, or the next one covers half of it
        draw.rectangle([seam - 5, 0, seam + 5, H], fill=BLACK)
    if grid:
        for f in range(1, 10):
            draw.line([(f * W / 10, 0), (f * W / 10, H)], fill=(255, 0, 0))
            draw.line([(0, f * H / 10), (W, f * H / 10)], fill=(255, 0, 0))
            draw.text((f * W / 10 + 2, 2), f".{f}", fill=(255, 0, 0))
            draw.text((2, f * H / 10 + 2), f".{f}", fill=(255, 0, 0))
        return canvas
    if not FONT.exists():
        raise FileNotFoundError(f"Font missing: {FONT} (Anton Regular)")
    fields = fields or {"num": "01", "chapter": "Chapter 1"}
    for lab in spec.get("labels", []):
        size = lab.get("size", 84)
        font = ImageFont.truetype(str(FONT), size)
        text = lab["text"].format(**fields)
        centre = (lab["at"][0] * W, lab["at"][1] * H)
        stroke = max(6, size // 9)
        # Kept inside the frame: a {num} that grows (01 -> 01-03+07) pushes its
        # label in from the edge instead of off it.
        box = draw.multiline_textbbox(centre, text, font=font, anchor="mm", align="center",
                                      spacing=0, stroke_width=stroke)
        margin = 12
        centre = (centre[0] + max(0, margin - box[0]) - max(0, box[2] - (W - margin)),
                  centre[1] + max(0, margin - box[1]) - max(0, box[3] - (H - margin)))
        if "to" in lab:
            box = draw.multiline_textbbox(centre, text, font=font, anchor="mm", align="center",
                                          spacing=0, stroke_width=stroke)
            tip = (lab["to"][0] * W, lab["to"][1] * H)
            # The arrow starts at the label's edge facing the target; the text
            # is drawn last so the arrow tucks under it.
            bx, by = min(max(tip[0], box[0]), box[2]), min(max(tip[1], box[1]), box[3])
            angle = math.atan2(tip[1] - by, tip[0] - bx)
            _arrow(draw, (bx + 12 * math.cos(angle), by + 12 * math.sin(angle)), tip)
        draw.multiline_text(centre, text, font=font, fill=YELLOW, anchor="mm", align="center",
                            spacing=0, stroke_width=stroke, stroke_fill=BLACK)
    return canvas
