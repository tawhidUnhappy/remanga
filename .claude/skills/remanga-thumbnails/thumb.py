"""Recap thumbnails (1280x720) from a chapter's own cut panels: panels side by
side, yellow Anton labels in a black outline, block arrows aimed at faces.
House style from AMV_CD/amv/shorts/thumb.py and /mnt/datadisk/thumbnail_examples.

    python thumb.py sheet  PROJECT [CHAPTER]   contact sheets of every panel, named, to pick from
    python thumb.py grid   specs.json          render without labels, 10% grid drawn - read positions off it
    python thumb.py render specs.json          the thumbnail, saved beside the chapter's video

Run with remanga's .venv/bin/python (it has Pillow). A spec (see specs.example.json):

    {"<key>": {"project": "...", "chapter": "1",
               "tiles":  [{"panel": "001_012_01", "w": 0.55, "zoom": 1.25, "cx": 0.5, "cy": 0.35}, ...],
               "labels": [{"text": "SADIST\\nPRINCESS", "at": [0.15, 0.74], "to": [0.29, 0.38], "size": 84}]}}

tiles: `w` is the tile's share of the width (they add up to 1), `zoom` crops in, `cx`/`cy`
the crop centre as fractions of the PANEL. labels: `at` the label centre, `to` the arrow tip,
both as fractions of the 1280x720 CANVAS - read them off a grid render, never guess."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
YELLOW, BLACK = (255, 230, 0), (8, 8, 8)
FONT = Path("/mnt/datadisk/AMV_CD/assets/fonts/Anton-Regular.ttf")
PROJECTS = Path(__file__).resolve().parents[3] / "projects"
SCRATCH = Path("/tmp/remanga-thumbs")


def panel_path(project: str, chapter: str, panel: str) -> Path:
    return PROJECTS / project / "chapters" / f"chapter_{chapter}" / "panels" / f"{panel}.png"


def tile(project: str, chapter: str, t: dict, box_w: int) -> Image.Image:
    """The panel cropped to the tile's shape around (cx, cy), scaled to fill it."""
    im = Image.open(panel_path(project, chapter, t["panel"])).convert("RGB")
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


def arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], tip: tuple[float, float], width: float = 30) -> None:
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


def compose(spec: dict, grid: bool) -> Image.Image:
    chapter = str(spec.get("chapter", "1"))
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    x, seams = 0, []
    for k, t in enumerate(spec["tiles"]):
        w = W - x if k == len(spec["tiles"]) - 1 else round(t["w"] * W)
        canvas.paste(tile(spec["project"], chapter, t, w), (x, 0))
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
        sys.exit(f"Font missing: {FONT} (Anton Regular, from the AMV project)")
    for lab in spec.get("labels", []):
        size = lab.get("size", 84)
        font = ImageFont.truetype(str(FONT), size)
        centre = (lab["at"][0] * W, lab["at"][1] * H)
        stroke = max(6, size // 9)
        box = draw.multiline_textbbox(centre, lab["text"], font=font, anchor="mm", align="center",
                                      spacing=0, stroke_width=stroke)
        tip = (lab["to"][0] * W, lab["to"][1] * H)
        # The arrow starts at the label's edge facing the target; the text is
        # drawn last so the arrow tucks under it.
        bx, by = min(max(tip[0], box[0]), box[2]), min(max(tip[1], box[1]), box[3])
        angle = math.atan2(tip[1] - by, tip[0] - bx)
        arrow(draw, (bx + 12 * math.cos(angle), by + 12 * math.sin(angle)), tip)
        draw.multiline_text(centre, lab["text"], font=font, fill=YELLOW, anchor="mm", align="center",
                            spacing=0, stroke_width=stroke, stroke_fill=BLACK)
    return canvas


def sheets(project: str, chapter: str) -> None:
    """Every panel of the chapter, 60 to a sheet, each named - to pick from."""
    files = sorted(panel_path(project, chapter, "x").parent.glob("*.png"))
    cols, cw, ch = 10, 240, 300
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(files), 60):
        chunk = files[start:start + 60]
        sheet = Image.new("RGB", (cols * cw, ((len(chunk) + cols - 1) // cols) * ch), "white")
        draw = ImageDraw.Draw(sheet)
        for i, f in enumerate(chunk):
            im = Image.open(f).convert("RGB")
            im.thumbnail((cw - 6, ch - 24))
            x, y = (i % cols) * cw, (i // cols) * ch
            sheet.paste(im, (x + 3, y + 20))
            draw.text((x + 4, y + 3), f.stem, fill="red")
        out = SCRATCH / f"sheet_{project}_{chapter}_{start // 60}.jpg"
        sheet.save(out, quality=80)
        print(out)


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("sheet", "grid", "render"):
        sys.exit(__doc__)
    mode = sys.argv[1]
    if mode == "sheet":
        sheets(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "1")
        return
    for key, spec in json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")).items():
        chapter = str(spec.get("chapter", "1"))
        if mode == "grid":
            SCRATCH.mkdir(parents=True, exist_ok=True)
            out = SCRATCH / f"{key}_grid.jpg"
        else:
            out = PROJECTS / spec["project"] / "video" / f"chapter_{chapter}" / \
                f"{spec['project']}_ch{chapter}_thumbnail.jpg"
            out.parent.mkdir(parents=True, exist_ok=True)
        compose(spec, grid=mode == "grid").save(out, quality=92)
        print(out)


if __name__ == "__main__":
    main()
