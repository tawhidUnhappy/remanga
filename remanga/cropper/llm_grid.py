"""Drawing one gridded page for the LLM crop workflow (prompts/llm_crop.md
<grid>).

A page becomes a square image: the page scaled evenly to fit, anchored at the
top-left corner, black everywhere else, and a green ruler grid across the
whole square in the 0-1000 units Gemini's bounding boxes already use
(`[ymin, xmin, ymax, xmax]`, normalised to the image).

Square, so a grid unit is the same number of pixels across as down - on a
manga page itself one unit of y is about 1.4 units of x, which is one more
thing a model has to correct for while estimating. Top-left, so a position
on the page is a position on the square divided by one factor per axis, with
no offset to subtract (see PageExtent). And nothing is drawn outside the
square, so the image edge IS the ruler's 0 and 1000: Gemini's own box frame
and the labels it reads can never disagree.

The spacing (faint lines every 50 units, labeled lines every 100) was chosen
by rendering real pages from this repo and shrinking them to roughly the size
a model sees: lines every 25 turned screentone into noise and crossed nearly
every bubble, and lines only every 100 left too few cells to estimate
inside."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

GRID_GREEN = (0, 230, 0)
LABEL_INK = (0, 105, 0)
PADDING_COLOR = (0, 0, 0)
# Line opacity. The faint lines still read when a 1600px square is shrunk to
# ~768px, without hiding the art underneath them at full size.
LABELED_ALPHA = 175
FAINT_ALPHA = 95
LABEL_TAG_ALPHA = 220

# EXIF orientations that turn the stored image a quarter turn, swapping width
# and height once applied.
_QUARTER_TURNS = {5, 6, 7, 8}


@dataclass(frozen=True)
class PageExtent:
    """Where a page sits inside its square, in grid units. It always starts
    at (0, 0) and ends at (ymax, xmax); its longer side reaches 1000."""

    ymax: float
    xmax: float

    @property
    def box(self) -> list[int]:
        """The page's area as `[ymin, xmin, ymax, xmax]`, the way
        chapter_info.json states it."""
        return [0, 0, round(self.ymax), round(self.xmax)]

    def to_page_box(self, box) -> list[int]:
        """A box measured on the square, as the same box normalised to the
        page itself - crops.json's `box_1000`. Whatever reaches into the black
        padding is clipped to the page's edge."""
        ymin, xmin, ymax, xmax = box
        return [
            _clip(ymin * 1000 / self.ymax), _clip(xmin * 1000 / self.xmax),
            _clip(ymax * 1000 / self.ymax), _clip(xmax * 1000 / self.xmax),
        ]


def _clip(value: float) -> int:
    return max(0, min(1000, round(value)))


def page_extent(width: int, height: int) -> PageExtent:
    longer = max(width, height, 1)
    return PageExtent(ymax=1000.0 * height / longer, xmax=1000.0 * width / longer)


def oriented_size(path: Path) -> tuple[int, int]:
    """A page's (width, height) as the cropper sees it - after the EXIF
    rotation crop_page applies - read without decoding the pixels."""
    with Image.open(path) as img:
        width, height = img.size
        orientation = img.getexif().get(0x0112)
    return (height, width) if orientation in _QUARTER_TURNS else (width, height)


def _pixel(value: int, size: int) -> int:
    return min(size - 1, round(value * size / 1000))


def _tag(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
         font: ImageFont.ImageFont, anchor: str) -> None:
    """Dark green text on a white tag, readable over art and over black."""
    left, top, right, bottom = draw.textbbox(xy, text, font=font, anchor=anchor)
    draw.rectangle([left - 3, top - 2, right + 3, bottom + 2], fill=(255, 255, 255, LABEL_TAG_ALPHA))
    draw.text(xy, text, font=font, fill=(*LABEL_INK, 255), anchor=anchor)


def _stamp(draw: ImageDraw.ImageDraw, text: str, size: int, width: int, height: int) -> None:
    """The page ID, in the black padding whenever there is room for it - the
    strip to the right of a tall page, the strip below a wide one - so it
    covers no artwork. A page close to square has no such strip, and gets
    the stamp over its top edge, under the labels."""
    font = ImageFont.load_default(size=max(14, round(size / 50)))
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    margin = round(size / 40)
    if size - width >= (right - left) + 2 * margin:
        _tag(draw, ((width + size) / 2, 2 * margin), text, font, "mt")
    elif size - height >= (bottom - top) + 2 * margin:
        _tag(draw, (size / 2, (height + size) / 2), text, font, "mm")
    else:
        _tag(draw, (size / 2, 2 * margin), text, font, "mt")


def render_grid_page(page: Image.Image, page_id: str, size: int = 1600,
                     line_step: int = 50, label_step: int = 100) -> Image.Image:
    """`page` on its black square, with the grid and its page ID stamp."""
    page = ImageOps.exif_transpose(page).convert("RGB")
    scale = size / max(page.size)
    width, height = max(1, round(page.width * scale)), max(1, round(page.height * scale))
    canvas = Image.new("RGB", (size, size), PADDING_COLOR)
    canvas.paste(page.resize((width, height), Image.Resampling.LANCZOS), (0, 0))

    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    labeled_width, faint_width = max(2, round(size / 530)), max(1, round(size / 800))
    for value in sorted(set(range(0, 1001, line_step)) | set(range(0, 1001, label_step))):
        labeled = value % label_step == 0
        at = _pixel(value, size)
        fill = (*GRID_GREEN, LABELED_ALPHA if labeled else FAINT_ALPHA)
        line_width = labeled_width if labeled else faint_width
        draw.line([(at, 0), (at, size)], fill=fill, width=line_width)
        draw.line([(0, at), (size, at)], fill=fill, width=line_width)

    font = ImageFont.load_default(size=max(12, round(size / 73)))
    for value in range(0, 1001, label_step):
        at = _pixel(value, size)
        # Anchors keep the 0 and 1000 labels inside the image.
        across = "l" if value == 0 else "r" if value == 1000 else "m"
        down = "t" if value == 0 else "d" if value == 1000 else "m"
        _tag(draw, (at, 3), str(value), font, across + "t")
        _tag(draw, (at, size - 3), str(value), font, across + "d")
        _tag(draw, (3, at), str(value), font, "l" + down)
        _tag(draw, (size - 3, at), str(value), font, "r" + down)

    _stamp(draw, page_id, size, width, height)
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
