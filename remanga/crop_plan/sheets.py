"""The pages as they are handed over to be checked: each page with its panel
boxes numbered in reading order on a grid of thousandths, and a long strip in
columns with a ruler of chapter rows and every cut labelled with its row.
The crop PDF (for an LLM) and Claude's sheets (crop.py show) are both drawn
here, so both look at the same picture.

A page is drawn at its own shape and nothing is added around it: an LLM's
boxes are fractions of the image it is shown, so an image with a margin
would shift every box it measures."""

from __future__ import annotations

from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFont

from remanga.crop_plan.grammar import Box

COLORS = [(255, 0, 64), (0, 170, 80), (0, 112, 255), (255, 140, 0), (176, 0, 255), (0, 170, 190),
          (255, 0, 192), (128, 128, 0)]
GRID = (0, 140, 255)
LABEL = (0, 70, 190)
CUT = (230, 0, 0)
COMPARE = (0, 170, 0)


# Hints are dashed, in colours none of the solid boxes use.
HINT_COLORS = {"figure": (230, 0, 120), "bubble": (0, 150, 150)}


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _dashed(d: ImageDraw.ImageDraw, rect: tuple[float, float, float, float], color, width: int, dash: int) -> None:
    x0, y0, x1, y1 = rect
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        length = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        steps = max(1, int(length // dash))
        for k in range(0, steps, 2):
            t0, t1 = k / steps, min(1.0, (k + 1) / steps)
            d.line([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                    (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)], fill=color, width=width)


def draw_page(image: Image.Image, boxes: Sequence[Box], *, stamp: str | None = None,
              width: int | None = None, max_side: int | None = None,
              hints: Sequence[dict] = ()) -> Image.Image:
    """The page with a grid line every 100 thousandths (labelled on all four
    edges) and its boxes outlined and numbered 1, 2, 3... in list order;
    `hints` (breakouts.py) dashed, their labels at the top right. `width`
    scales it to that width; `max_side` only ever shrinks it."""
    im = image.convert("RGB")
    scale = width / im.width if width else min(1.0, (max_side or max(im.size)) / max(im.size))
    if scale != 1.0:
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.LANCZOS)
    w, h = im.size
    d = ImageDraw.Draw(im, "RGBA")
    unit = max(w, h)
    small, big = _font(max(11, round(unit / 80))), _font(max(18, round(unit / 40)))
    halo = max(1, round(unit / 700))
    for g in range(100, 1000, 100):
        x, y = g * w / 1000, g * h / 1000
        d.line([(x, 0), (x, h)], fill=(*GRID, 70), width=1)
        d.line([(0, y), (w, y)], fill=(*GRID, 70), width=1)
        for at, anchor in (((x + 3, 2), "la"), ((x + 3, h - 2), "ld"), ((2, y + 2), "la"), ((w - 2, y + 2), "ra")):
            d.text(at, str(g), fill=LABEL, font=small, anchor=anchor, stroke_width=halo, stroke_fill="white")
    line = max(2, round(unit / 400))
    for i, (y0, x0, y1, x1) in enumerate(boxes):
        color = COLORS[i % len(COLORS)]
        rect = (x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000)
        d.rectangle(rect, outline=(*color, 215), width=line)
        corner = (rect[0] + line + 3, rect[1] + line + 3)
        tb = d.textbbox(corner, str(i + 1), font=big)
        d.rectangle((tb[0] - 5, tb[1] - 4, tb[2] + 5, tb[3] + 4), fill=(*color, 235))
        d.text(corner, str(i + 1), fill="white", font=big)
    for hint in hints:
        color = HINT_COLORS[hint["kind"]]
        y0, x0, y1, x1 = hint["box_1000"]
        rect = (x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000)
        _dashed(d, rect, (*color, 235), max(2, line - 1), dash=max(8, round(unit / 90)))
        # The label sits on top of the box's right corner, clear of what it outlines.
        corner = (rect[2], rect[1] - line - 4) if rect[1] > big.size + 12 else (rect[2] - line - 3, rect[1] + line + 3)
        tb = d.textbbox(corner, hint["label"], font=big, anchor="rd" if rect[1] > big.size + 12 else "ra")
        d.rectangle((tb[0] - 5, tb[1] - 4, tb[2] + 5, tb[3] + 4), fill=(255, 255, 255, 235), outline=(*color, 255),
                    width=max(2, line - 1))
        d.text(corner, hint["label"], fill=color, font=big, anchor="rd" if rect[1] > big.size + 12 else "ra")
    if stamp:
        at = (w / 2, h - small.size - 10)
        tb = d.textbbox(at, stamp, font=big, anchor="md")
        d.rectangle((tb[0] - 10, tb[1] - 6, tb[2] + 10, tb[3] + 6), fill=(0, 0, 0, 170))
        d.text(at, stamp, fill="white", font=big, anchor="md")
    return im


def strip_sheets(view, panels: Sequence[tuple[int, int]], *, rows: int = 2000, width: int = 420,
                 per_sheet: int = 3, compare: Sequence[int] = (), title: str = "") -> list[Image.Image]:
    """The strip in columns of `rows` chapter rows, each `width` px wide, with a
    ruler of chapter rows on the left (a label every 200 rows, a tick every
    50), every cut between `panels` as a red line labelled with its row, and
    a bar per panel on the right (numbered where it starts; rows no panel
    covers are hatched). `compare` rows are drawn as thin green cuts. Columns
    run top to bottom and then left to right, `per_sheet` to an image."""
    from remanga.crop_plan.strip import cuts_of

    cuts = cuts_of(list(panels))
    columns = [_column(view, index, top, rows, width, panels, cuts, compare)
               for index, run in enumerate(view.runs) for top in range(0, run.height, rows)]
    sheets = []
    head = _font(max(14, round(width / 22)))
    for start in range(0, len(columns), per_sheet):
        group = columns[start:start + per_sheet]
        header = head.size + 16
        sheet = Image.new("RGB", (sum(c.width for c in group) + 12 * (len(group) - 1),
                                  header + max(c.height for c in group)), (90, 90, 90))
        d = ImageDraw.Draw(sheet)
        first, last = group[0].info["rows"][0], group[-1].info["rows"][1]
        d.text((8, 8), f"{title}rows {first}-{last} - each column top to bottom, the columns left to right",
               fill="white", font=head)
        x = 0
        for column in group:
            sheet.paste(column, (x, header))
            x += column.width + 12
        sheets.append(sheet)
    return sheets


def _column(view, index: int, top: int, rows: int, width: int, panels, cuts, compare) -> Image.Image:
    run = view.runs[index]
    piece = view.image(index).crop((0, top, run.width, min(run.height, top + rows)))
    scale = width / run.width
    piece = piece.resize((width, max(1, round(piece.height * scale))), Image.Resampling.LANCZOS)
    font = _font(max(13, round(width / 24)))
    ruler, bar = font.size * 5, max(30, font.size * 2)
    col = Image.new("RGB", (ruler + width + bar, piece.height), "white")
    col.paste(piece, (ruler, 0))
    first, last = run.top + top, run.top + min(run.height, top + rows)
    col.info["rows"] = (first, last)
    d = ImageDraw.Draw(col, "RGBA")

    def y_of(row: int) -> float:
        return (row - first) * scale

    for row in range(first - first % 50 + 50, last, 50):
        y = y_of(row)
        d.line((ruler - (16 if row % 200 == 0 else 7), y, ruler, y), fill="black", width=2 if row % 200 == 0 else 1)
        if row % 200 == 0:
            d.text((ruler - 19, y), str(row), fill="black", font=font, anchor="rm")
    x0, x1 = ruler + width, ruler + width + bar
    covered = [(max(a, first), min(b, last)) for a, b in sorted(panels) if a < last and b > first]
    for number, (a, b) in enumerate(sorted(panels), start=1):
        if not (a < last and b > first):
            continue
        color = COLORS[2 + number % 2]   # blue and orange, clear of the red cuts
        d.rectangle((x0 + 3, y_of(max(a, first)), x1 - 3, y_of(min(b, last)) - 1), fill=(*color, 150))
        if first <= a:
            d.text((x0 + bar / 2, y_of(a) + 3), str(number), fill="white", font=font, anchor="ma",
                   stroke_width=2, stroke_fill="black")
    gap_top = first
    for a, b in [*covered, (last, last)]:
        if a > gap_top + 1:   # rows no panel covers: they are left out of the video
            d.rectangle((ruler, y_of(gap_top), x1, y_of(a)), fill=(110, 110, 110, 120))
            if y_of(a) - y_of(gap_top) > font.size + 6:
                d.text((ruler + width / 2, (y_of(gap_top) + y_of(a)) / 2), "no panel", fill="white", font=font,
                       anchor="mm", stroke_width=2, stroke_fill="black")
        gap_top = max(gap_top, b)
    for rows_drawn, color, thick in ((compare, COMPARE, 2), (cuts, CUT, 3)):
        for row in rows_drawn:
            if first <= row < last:
                y = y_of(row)
                d.line((ruler, y, x0, y), fill=(*color, 255), width=thick)
                if color == CUT:
                    tb = d.textbbox((ruler + 4, y), str(row), font=font, anchor="lm")
                    d.rectangle((tb[0] - 3, tb[1] - 3, tb[2] + 3, tb[3] + 3), fill=(*CUT, 255))
                    d.text((ruler + 4, y), str(row), fill="white", font=font, anchor="lm")
                else:
                    d.text((x0 - 4, y - 2), str(row), fill=(*COMPARE, 255), font=font, anchor="rd")
    return col
