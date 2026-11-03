"""A thumbnail laid out from an LLM's choices: which images, the face (or
subject) in each, the words. An LLM picks a strong image and a good hook,
but places things badly by eye - so it only says WHAT, as boxes on the image
it saw, and the layout is worked out here, the way a thumbnail designer
would:

- each tile is cropped around its subject at the framing asked for (a close
  face, a face and upper body, or the whole subject), the face a little above
  the middle so there is room under it for words - never enlarged past
  MAX_UPSCALE (a small panel blown up is only soft), never past the image's
  own edges, and shifted or tightened to keep out what the LLM asked to avoid
  (a speech balloon, a watermark, a logo);
- each label goes under or beside the face it names, never over a face,
  inside its own tile, clear of the other labels and of the bottom-right
  corner where YouTube prints the video's length; its size is the largest
  that fits, on one line or two balanced ones;
- an arrow, when asked for, stops short of the face;
- the CH badge takes the first free top or bottom-left corner.

The result is an ordinary thumbnail spec (remanga/video/thumbnail.py), so
it can still be tuned by hand."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from remanga.upload_plan.reply import Label, Tile, Variant
from remanga.video.thumbnail import FONT, H, W

# framing -> (the share of the tile's height the subject fills, where its middle sits from the top)
FRAMING = {"close": (0.62, 0.42), "medium": (0.42, 0.37), "wide": (0.86, 0.5)}
MAX_UPSCALE = 2.6
MARGIN = 18          # px between a label and the canvas or tile edge
GAP = 14             # px between a label and the face it names
DURATION_CORNER = (W * 0.8, H * 0.8, W, H)   # YouTube's length stamp
SIZE_RANGE = (54, 112)
BADGE_SIZE = 50
ARROW_GAP = 30       # an arrow's tip stays this far from the face
TINT_CONTRAST, COLOUR_SATURATION = 1.12, 1.15

Rect = tuple[float, float, float, float]   # x0, y0, x1, y1 in pixels


@dataclass
class Placed:
    """A tile as laid out: where on the canvas, and its subject there."""
    x0: int
    x1: int
    subject: Rect
    avoid: list[Rect]


def _overlap(a: Rect, b: Rect) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(r: Rect) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _px(box: tuple[int, int, int, int], size: tuple[int, int]) -> Rect:
    """[ymin, xmin, ymax, xmax] thousandths -> x0, y0, x1, y1 pixels."""
    w, h = size
    return (box[1] * w / 1000, box[0] * h / 1000, box[3] * w / 1000, box[2] * h / 1000)


def widths(tiles: list[Tile]) -> list[int]:
    """Each tile's width on the canvas, as thumbnail.compose lays them out:
    the shares asked for, the rest split evenly, the last tile what is left."""
    given = sum(t.share for t in tiles if t.share)
    free = [t for t in tiles if not t.share]
    rest = max(0.0, 1.0 - given) / len(free) if free else 0.0
    shares = [t.share or rest for t in tiles]
    total = sum(shares) or 1.0
    out = [round(s / total * W) for s in shares[:-1]]
    return [*out, W - sum(out)]


def crop_for(size: tuple[int, int], tile: Tile, tile_w: int) -> Rect:
    """The part of the image the tile shows, in its pixels, the tile's shape."""
    iw, ih = size
    sx0, sy0, sx1, sy1 = _px(tile.subject, size)
    fill, middle = FRAMING[tile.framing]
    aspect = tile_w / H
    ch = (sy1 - sy0) / fill
    cw = ch * aspect
    if sx1 - sx0 > cw * 0.9:            # a wide subject: its width decides
        cw = (sx1 - sx0) / 0.9
        ch = cw / aspect
    if ch < H / MAX_UPSCALE:            # never blown up past the cap
        ch = H / MAX_UPSCALE
        cw = ch * aspect
    shrink = min(1.0, iw / cw, ih / ch)  # never past the image's edges
    cw, ch = cw * shrink, ch * shrink
    cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2

    def placed(x: float, y: float, w: float, h: float) -> Rect:
        x, y = min(max(x, 0.0), iw - w), min(max(y, 0.0), ih - h)
        return (x, y, x + w, y + h)

    base = placed(cx - cw / 2, cy - middle * ch, cw, ch)
    avoid = [_px(a, size) for a in tile.avoid]
    if not avoid:
        return base
    subject = (sx0, sy0, sx1, sy1)
    best, best_score = base, math.inf
    for tighter in (1.0, 0.9, 0.8):
        w, h = cw * tighter, ch * tighter
        if h < min(ch, H / MAX_UPSCALE):
            continue
        for dx in (0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3):
            for dy in (0, -0.1, 0.1, -0.2, 0.2):
                rect = placed(cx - w / 2 + dx * w, cy - middle * h + dy * h, w, h)
                if _overlap(rect, subject) < _area(subject) * 0.97:   # the subject must stay in whole
                    continue
                hidden = sum(_overlap(rect, a) for a in avoid) / _area(rect)
                score = hidden * 10 + abs(dx) + abs(dy) + (1 - tighter)
                if score < best_score:
                    best, best_score = rect, score
    return best


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


_SCRATCH = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def _measure(text: str, size: int) -> tuple[float, float]:
    """A label's width and height as thumbnail.compose draws it (outline included)."""
    box = _SCRATCH.multiline_textbbox((0, 0), text, font=_font(size), anchor="mm", align="center", spacing=0,
                                      stroke_width=max(6, size // 9))
    return box[2] - box[0], box[3] - box[1]


def _layouts(text: str) -> list[str]:
    """The label on one line, and split in two at each space - the most balanced first."""
    words = text.split()
    splits = [" ".join(words[:i]) + "\n" + " ".join(words[i:]) for i in range(1, len(words))]
    splits.sort(key=lambda s: max(len(part) for part in s.split("\n")))
    return [text, *splits[:2]]


def _sized(text: str, max_w: float, max_h: float) -> list[tuple[str, int, float, float]]:
    """Every (text, size, width, height) that fits, the biggest first; one
    line before two at the same size."""
    out = []
    top = SIZE_RANGE[1] if len(text) <= 8 else SIZE_RANGE[1] - 16
    for size in range(top, SIZE_RANGE[0] - 1, -4):
        for layout in _layouts(text):
            w, h = _measure(layout, size)
            if w <= max_w and h <= max_h:
                out.append((layout, size, w, h))
    return out


def _rect(cx: float, cy: float, w: float, h: float) -> Rect:
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _spots(tile: Placed, w: float, h: float) -> list[tuple[float, float, float]]:
    """Where a label could go on its tile: (rank, x, y) - under the face
    first, then beside it, then the tile's bottom and top bands, then above."""
    sx0, sy0, sx1, sy1 = tile.subject
    scx, scy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
    xs = [scx, (tile.x0 + tile.x1) / 2, tile.x0 + MARGIN + w / 2, tile.x1 - MARGIN - w / 2]
    spots = [(0.0, x, sy1 + GAP + h / 2) for x in xs]
    for y in (scy, sy1 - h / 2, sy0 + h / 2):
        spots += [(1.0, sx0 - GAP - w / 2, y), (1.0, sx1 + GAP + w / 2, y)]
    spots += [(1.5, x, H - MARGIN - h / 2) for x in xs] + [(2.0, x, MARGIN + h / 2) for x in xs]
    spots += [(2.5, x, sy0 - GAP - h / 2) for x in xs]
    return spots


def _fits(rect: Rect, tile: Placed, faces: list[Rect], taken: list[Rect], face_room: float) -> bool:
    if rect[0] < tile.x0 + MARGIN or rect[2] > tile.x1 - MARGIN or rect[1] < MARGIN or rect[3] > H - MARGIN:
        return False
    if _overlap(rect, DURATION_CORNER) > 0:
        return False
    if any(_overlap(rect, face) > face_room * _area(rect) for face in faces):
        return False
    pad = 8
    return not any(_overlap((rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad), t) > 0 for t in taken)


def place_label(label: Label, tile: Placed, faces: list[Rect], taken: list[Rect]) -> dict:
    """A label as thumbnail.compose takes it: {text, at, size, color[, to]}."""
    max_w, max_h = tile.x1 - tile.x0 - 2 * MARGIN, H * 0.42
    scx, scy = (tile.subject[0] + tile.subject[2]) / 2, (tile.subject[1] + tile.subject[3]) / 2
    for face_room in (0.03, 0.15):      # under the chin only when nothing else is free
        for text, size, w, h in _sized(label.text, max_w, max_h):
            best, best_score = None, math.inf
            for rank, x, y in _spots(tile, w, h):
                rect = _rect(x, y, w, h)
                if not _fits(rect, tile, faces, taken, face_room):
                    continue
                score = rank + math.hypot(x - scx, y - scy) / 400 + 3 * sum(
                    _overlap(rect, a) for a in tile.avoid) / _area(rect)
                if score < best_score:
                    best, best_score = rect, score
            if best:
                taken.append(best)
                at = [round((best[0] + best[2]) / 2 / W, 4), round((best[1] + best[3]) / 2 / H, 4)]
                out = {"text": text, "at": at, "size": size, "color": label.color}
                if label.arrow:
                    tip = _arrow_tip(best, tile.subject)
                    if tip:
                        out["to"] = [round(tip[0] / W, 4), round(tip[1] / H, 4)]
                return out
    # Nothing free anywhere: the tile's bottom band, as small as it goes.
    text, size, w, h = (_sized(label.text, max_w, max_h) or [(label.text, SIZE_RANGE[0], 0, 0)])[-1]
    return {"text": text, "at": [round((tile.x0 + tile.x1) / 2 / W, 4), round(1 - (MARGIN + h / 2) / H, 4)],
            "size": size, "color": label.color}


def _arrow_tip(label: Rect, face: Rect) -> tuple[float, float] | None:
    """Where an arrow from the label towards the face stops: ARROW_GAP short
    of it. None when the label is already beside it."""
    lx, ly = (label[0] + label[2]) / 2, (label[1] + label[3]) / 2
    room = (face[0] - ARROW_GAP, face[1] - ARROW_GAP, face[2] + ARROW_GAP, face[3] + ARROW_GAP)
    fx, fy = (face[0] + face[2]) / 2, (face[1] + face[3]) / 2
    # Walk from the label's middle towards the face's until inside the room around it.
    steps = 200
    for k in range(steps + 1):
        x, y = lx + (fx - lx) * k / steps, ly + (fy - ly) * k / steps
        if room[0] <= x <= room[2] and room[1] <= y <= room[3]:
            inside_label = label[0] <= x <= label[2] and label[1] <= y <= label[3]
            edge = (min(max(x, label[0]), label[2]), min(max(y, label[1]), label[3]))
            if inside_label or math.hypot(x - edge[0], y - edge[1]) < 40:
                return None
            return (x, y)
    return None


def place_badge(text_width_sample: str, faces: list[Rect], taken: list[Rect]) -> dict | None:
    """The CH badge in the first free corner: top left, top right, bottom left."""
    w, h = _measure(text_width_sample, BADGE_SIZE)
    for cx, cy in ((MARGIN + w / 2, MARGIN + h / 2), (W - MARGIN - w / 2, MARGIN + h / 2),
                   (MARGIN + w / 2, H - MARGIN - h / 2)):
        rect = _rect(cx, cy, w, h)
        if not any(_overlap(rect, f) > 0.03 * _area(rect) for f in faces) and not any(
                _overlap(rect, t) > 0 for t in taken):
            taken.append(rect)
            return {"text": "CH {num}", "at": [round(cx / W, 4), round(cy / H, 4)], "size": BADGE_SIZE}
    return None


def spec_for(project: str, variant: Variant, record: dict) -> dict:
    """The thumbnail spec for one set, its images from the upload PDF's record."""
    tiles, placed = [], []
    x = 0
    for tile, width in zip(variant.tiles, widths(variant.tiles), strict=True):
        candidate = record["candidates"][tile.image]
        size = tuple(candidate["size"])
        crop = crop_for(size, tile, width)
        scale = width / (crop[2] - crop[0])
        sx0, sy0, sx1, sy1 = _px(tile.subject, size)

        def on_canvas(r: Rect, crop: Rect = crop, scale: float = scale, x: int = x) -> Rect:
            return (x + (r[0] - crop[0]) * scale, (r[1] - crop[1]) * scale,
                    x + (r[2] - crop[0]) * scale, (r[3] - crop[1]) * scale)

        placed.append(Placed(x, x + width, on_canvas((sx0, sy0, sx1, sy1)),
                             [on_canvas(_px(a, size)) for a in tile.avoid]))
        entry = {("page" if candidate["kind"] == "page" else "panel"):
                 candidate["file"] if candidate["kind"] == "page" else tile.image,
                 "chapter": candidate["chapter"], "w": round(width / W, 4),
                 "box": [round(v) for v in crop], "zoom": 1.0, "cx": 0.5, "cy": 0.5}
        if tile.tint:
            entry.update(tint=tile.tint, contrast=TINT_CONTRAST)
        elif candidate["colour"]:
            entry["saturation"] = COLOUR_SATURATION
        tiles.append(entry)
        x += width
    faces = [p.subject for p in placed]
    taken: list[Rect] = []
    labels = [place_label(lab, placed[lab.tile - 1], faces, taken) for lab in variant.labels]
    if variant.badge:
        badge = place_badge(f"CH {record.get('label_num') or '00'}", faces, taken)
        if badge:
            labels.append(badge)
    return {"project": project, "chapter": record["chapters"][0], "tiles": tiles, "labels": labels}
