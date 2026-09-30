"""Minimal, dependency-free PDF assembler.

Why not just `Image.save(path, "PDF", save_all=True, append_images=...)`?
Pillow's own PDF writer re-encodes RGB/L/CMYK images as lossy JPEG
(`/Filter /DCTDecode`) unconditionally - verified directly against this
project's own pages, there is no save parameter that makes it embed
them losslessly. Its only genuinely lossless path is palette ("P") mode,
which means quantizing full-color/grayscale art down to <=256 colors first -
real quality loss, not acceptable for what remanga.pdf.builder needs.

So this builds the PDF bytes directly instead, using PDF's own native
lossless raster path: each image is embedded as a `/FlateDecode`-compressed
raw bitmap, filtered first for a better ratio - either TIFF Predictor 2
(`encode_predictor2`/`decode_predictor2` below) or PNG's own per-row filters,
taken straight out of a PNG file (`png_idat_stream`): a PNG's IDAT data *is*
a PDF FlateDecode stream with /Predictor 15, byte for byte.

The lossy options are a caller's explicit choice, never a default: a page can
instead carry a palette image (a quantized PNG's IDAT and PLTE, as an
/Indexed color space) or a baseline JPEG as-is (`/DCTDecode`), which is how
remanga.pdf.builder keeps a PDF under its size cap when lossless pages
alone would not fit.

Deliberately narrow: this only ever needs to do exactly two kinds of page - a
full-page raster image, and a page of left-aligned lines of plain text in one
of the PDF standard 14 fonts (no font file to embed) - so that's all it
implements. Not a general-purpose PDF library.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from remanga.pdf.textpage import TEXT_FONT, text_layout, text_page_content

# The base layout for the text page, in points. A bigger page (the image
# pages set the size - see build_pdf) scales all of it by the same factor,
# and how many lines fit follows from that - see text_layout.


@dataclass
class ImagePage:
    """One full-page raster image. `data` must already be the final stream
    payload. With `filter` "FlateDecode" that is zlib-compressed raw
    top-to-bottom RGB/grayscale bytes, filtered first as `predictor` says (2:
    encode_predictor2; 15: PNG row filters, see png_idat_stream; None: none).
    With "DCTDecode" it is a whole JPEG file, and `predictor` is ignored.
    `colors` is 3 for RGB, 1 for grayscale or palette indices. `palette`, when
    set, is the RGB triples those indices point into, and `bits` their width.
    `lossless` is the caller's word for whether the pixels are the source's."""
    width: int
    height: int
    data: bytes
    colors: int = 3
    predictor: int | None = 2
    filter: str = "FlateDecode"
    palette: bytes | None = None
    bits: int = 8
    lossless: bool = True


def build_pdf(image_pages: Sequence[ImagePage], info_lines: Sequence[str],
              canvas: tuple[int, int] | None = None) -> bytes:
    """Assembles one complete PDF file: one or more leading text pages
    rendering `info_lines` as real, extractable text (paginated - see
    text_layout - so a long manifest still gets a plain flowing
    list instead of overflowing a single page), followed by one page per
    `image_pages`, in order.

    `canvas` is the size EVERY image page gets, with the image centred on
    black - panels are cut at whatever size they are, and a PDF whose pages
    change shape every time you scroll is hard to read (user request). The
    default is the biggest page given here; the caller passes the biggest of
    the whole chapter so the parts of a split PDF match each other. The image
    bytes are untouched either way: this is page geometry, not re-encoding."""
    if canvas is None:
        canvas = (max((p.width for p in image_pages), default=1),
                  max((p.height for p in image_pages), default=1))
    page_w = max(canvas[0], max((p.width for p in image_pages), default=1))
    page_h = max(canvas[1], max((p.height for p in image_pages), default=1))
    objects: list[bytes] = [b""]  # 1-indexed - objects[0] is an unused placeholder

    def add_object(body: bytes) -> int:
        objects.append(body)
        return len(objects) - 1

    catalog_id = add_object(b"")  # filled in once pages_id is known
    pages_id = add_object(b"")    # filled in once every page is built
    font_id = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /" + TEXT_FONT.encode("ascii") + b" >>"
    )

    kids: list[int] = []

    lines_per_page = text_layout(page_w, page_h)[3]
    text_pages = [
        info_lines[i:i + lines_per_page]
        for i in range(0, len(info_lines), lines_per_page)
    ] or [[]]
    for page_lines in text_pages:
        content = text_page_content(page_lines, page_w, page_h)
        content_id = add_object(
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
        )
        kids.append(add_object(
            b"<< /Type /Page /Parent " + str(pages_id).encode("ascii") + b" 0 R "
            b"/MediaBox [0 0 " + str(page_w).encode("ascii") + b" " +
            str(page_h).encode("ascii") + b"] "
            b"/Resources << /Font << /F1 " + str(font_id).encode("ascii") + b" 0 R >> >> "
            b"/Contents " + str(content_id).encode("ascii") + b" 0 R >>"
        ))

    for img in image_pages:
        colorspace = b"/DeviceRGB" if img.colors == 3 else b"/DeviceGray"
        if img.palette is not None:
            colorspace = (b"[/Indexed /DeviceRGB " + str(len(img.palette) // 3 - 1).encode("ascii") +
                          b" <" + img.palette.hex().encode("ascii") + b">]")
        decode_parms = b""
        if img.filter == "FlateDecode" and img.predictor is not None:
            decode_parms = (
                b" /DecodeParms << /Predictor " + str(img.predictor).encode("ascii") +
                b" /Colors " + str(img.colors).encode("ascii") +
                b" /BitsPerComponent " + str(img.bits).encode("ascii") +
                b" /Columns " + str(img.width).encode("ascii") + b" >>"
            )
        image_id = add_object(
            b"<< /Type /XObject /Subtype /Image /Width " + str(img.width).encode("ascii") +
            b" /Height " + str(img.height).encode("ascii") +
            b" /ColorSpace " + colorspace +
            b" /BitsPerComponent " + str(img.bits).encode("ascii") +
            b" /Filter /" + img.filter.encode("ascii") + decode_parms +
            b" /Length " + str(len(img.data)).encode("ascii") + b" >>\nstream\n" +
            img.data + b"\nendstream"
        )
        # Black page, then the panel centred on it - `re f` fills the whole
        # MediaBox, `cm` places the image at its own size.
        left, bottom = (page_w - img.width) // 2, (page_h - img.height) // 2
        img_content = (
            f"0 0 0 rg 0 0 {page_w} {page_h} re f "
            f"q {img.width} 0 0 {img.height} {left} {bottom} cm /Im0 Do Q"
        ).encode("ascii")
        img_content_id = add_object(
            b"<< /Length " + str(len(img_content)).encode("ascii") + b" >>\nstream\n" +
            img_content + b"\nendstream"
        )
        kids.append(add_object(
            b"<< /Type /Page /Parent " + str(pages_id).encode("ascii") + b" 0 R "
            b"/MediaBox [0 0 " + str(page_w).encode("ascii") + b" " +
            str(page_h).encode("ascii") + b"] "
            b"/Resources << /XObject << /Im0 " + str(image_id).encode("ascii") + b" 0 R >> >> "
            b"/Contents " + str(img_content_id).encode("ascii") + b" 0 R >>"
        ))

    objects[pages_id] = (
        b"<< /Type /Pages /Kids [" +
        b" ".join(f"{k} 0 R".encode("ascii") for k in kids) +
        b"] /Count " + str(len(kids)).encode("ascii") + b" >>"
    )
    objects[catalog_id] = b"<< /Type /Catalog /Pages " + str(pages_id).encode("ascii") + b" 0 R >>"

    return _assemble(objects, catalog_id)


def _assemble(objects: list[bytes], catalog_id: int) -> bytes:
    """Writes every object in order, then a byte-accurate xref table and
    trailer - the bookkeeping every PDF reader expects to be able to jump
    straight to any object by its recorded offset."""
    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * len(objects)
    for i in range(1, len(objects)):
        offsets[i] = len(buf)
        buf += f"{i} 0 obj\n".encode("ascii") + objects[i] + b"\nendobj\n"

    xref_offset = len(buf)
    buf += f"xref\n0 {len(objects)}\n".encode("ascii")
    buf += b"0000000000 65535 f \n"
    for i in range(1, len(objects)):
        buf += f"{offsets[i]:010d} 00000 n \n".encode("ascii")

    buf += (
        b"trailer\n<< /Size " + str(len(objects)).encode("ascii") +
        b" /Root " + str(catalog_id).encode("ascii") + b" 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode("ascii") + b"\n%%EOF"
    )
    return bytes(buf)
