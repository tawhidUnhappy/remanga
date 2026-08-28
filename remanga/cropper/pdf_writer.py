"""Minimal, dependency-free PDF assembler.

Why not just `Image.save(path, "PDF", save_all=True, append_images=...)`?
Pillow's own PDF writer re-encodes RGB/L/CMYK images as lossy JPEG
(`/Filter /DCTDecode`) unconditionally - verified directly against this
project's own panel images, there is no save parameter that makes it embed
them losslessly. Its only genuinely lossless path is palette ("P") mode,
which means quantizing full-color/grayscale art down to <=256 colors first -
real quality loss, not acceptable for what remanga.cropper.llm_pdf needs.

So this builds the PDF bytes directly instead, using PDF's own native
lossless raster path: each image is embedded as a `/FlateDecode`-compressed
raw bitmap (optionally TIFF-Predictor-2-filtered first for better ratio,
`encode_predictor2`/`decode_predictor2` below) - the same class of lossless
compression a PNG uses internally, just packaged the way PDF expects it.

Deliberately narrow: this only ever needs to do exactly two kinds of page - a
full-page raster image, and a page of left-aligned lines of plain text in one
of the PDF standard 14 fonts (no font file to embed) - so that's all it
implements. Not a general-purpose PDF library.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

# US Letter-ish page size in points (1/72 inch) for the leading text page.
# Image pages use their own pixel dimensions directly as the page size
# (1 image pixel = 1 PDF point), so no image ever needs rescaling/letterboxing.
_TEXT_PAGE_SIZE = (612, 792)
_TEXT_FONT = "Helvetica"
_TEXT_SIZE = 11
_TEXT_LEADING = 15
_TEXT_MARGIN = 54


@dataclass
class ImagePage:
    """One full-page raster image. `flate_data` must already be the final
    stream payload - zlib-compressed raw top-to-bottom RGB/grayscale bytes,
    optionally TIFF-Predictor-2-filtered first (see encode_predictor2) if
    `predictor` is 2. `colors` is 3 for RGB, 1 for grayscale."""
    width: int
    height: int
    flate_data: bytes
    colors: int = 3
    predictor: Optional[int] = 2


def encode_predictor2(arr: np.ndarray) -> bytes:
    """TIFF Predictor 2 (per-row, per-component horizontal differencing,
    matching the PDF/TIFF6 spec exactly) then zlib - PDF's own native
    lossless image representation, and what `ImagePage.flate_data` should
    hold when `predictor=2`. `arr` is (H, W, colors) uint8. Any standards-
    compliant PDF reader decodes this back exactly; `decode_predictor2`
    (below) implements the same inverse purely so a caller can self-verify a
    round-trip before trusting the encoded bytes (see llm_pdf.py)."""
    diff = arr.copy()
    diff[:, 1:, :] = arr[:, 1:, :] - arr[:, :-1, :]
    return zlib.compress(diff.astype(np.uint8).tobytes(), 9)


def decode_predictor2(flate_data: bytes, shape: Tuple[int, int, int]) -> np.ndarray:
    """Inverse of encode_predictor2 - decompresses and reverses the
    per-row horizontal differencing via a cumulative sum (mod 256) along the
    column axis, which telescopes back to the original values exactly."""
    diff = np.frombuffer(zlib.decompress(flate_data), dtype=np.uint8).reshape(shape)
    return (np.cumsum(diff.astype(np.int32), axis=1) % 256).astype(np.uint8)


def encode_flate_raw(arr: np.ndarray) -> bytes:
    """Plain zlib over the raw bitmap, no predictor - a simpler, strictly more
    robust fallback `ImagePage(..., predictor=None)` can use if
    encode_predictor2 ever fails to round-trip (see llm_pdf.py). Produces a
    noticeably larger stream (no horizontal decorrelation), but every step is
    just zlib, nothing left to get subtly wrong."""
    return zlib.compress(arr.astype(np.uint8).tobytes(), 9)


def decode_flate_raw(flate_data: bytes, shape: Tuple[int, int, int]) -> np.ndarray:
    return np.frombuffer(zlib.decompress(flate_data), dtype=np.uint8).reshape(shape)


def _escape_pdf_text(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _text_page_content(lines: Sequence[str]) -> bytes:
    x, y = _TEXT_MARGIN, _TEXT_PAGE_SIZE[1] - _TEXT_MARGIN
    parts = [f"BT /F1 {_TEXT_SIZE} Tf {_TEXT_LEADING} TL {x} {y} Td"]
    for i, line in enumerate(lines):
        if i > 0:
            parts.append("T*")
        # Standard-14 Helvetica only covers Latin-1 - this text page is
        # metadata (chapter/part identity), not panel content, so a
        # non-Latin-1 character here becomes "?" rather than pulling in a
        # Unicode-capable embedded font for one info page. Never affects the
        # actual panel images, which stay pixel-exact regardless.
        parts.append(f"({_escape_pdf_text(line)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", errors="replace")


def build_pdf(image_pages: Sequence[ImagePage], info_lines: Sequence[str]) -> bytes:
    """Assembles one complete PDF file: a leading text page rendering
    `info_lines` as real, extractable text, followed by one full-page image
    per `image_pages`, in order."""
    objects: List[bytes] = [b""]  # 1-indexed - objects[0] is an unused placeholder

    def add_object(body: bytes) -> int:
        objects.append(body)
        return len(objects) - 1

    catalog_id = add_object(b"")  # filled in once pages_id is known
    pages_id = add_object(b"")    # filled in once every page is built
    font_id = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /" + _TEXT_FONT.encode("ascii") + b" >>"
    )

    kids: List[int] = []

    content = _text_page_content(info_lines)
    content_id = add_object(
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
    )
    kids.append(add_object(
        b"<< /Type /Page /Parent " + str(pages_id).encode("ascii") + b" 0 R "
        b"/MediaBox [0 0 " + str(_TEXT_PAGE_SIZE[0]).encode("ascii") + b" " +
        str(_TEXT_PAGE_SIZE[1]).encode("ascii") + b"] "
        b"/Resources << /Font << /F1 " + str(font_id).encode("ascii") + b" 0 R >> >> "
        b"/Contents " + str(content_id).encode("ascii") + b" 0 R >>"
    ))

    for img in image_pages:
        colorspace = b"/DeviceRGB" if img.colors == 3 else b"/DeviceGray"
        decode_parms = b""
        if img.predictor is not None:
            decode_parms = (
                b" /DecodeParms << /Predictor " + str(img.predictor).encode("ascii") +
                b" /Colors " + str(img.colors).encode("ascii") +
                b" /BitsPerComponent 8 /Columns " + str(img.width).encode("ascii") + b" >>"
            )
        image_id = add_object(
            b"<< /Type /XObject /Subtype /Image /Width " + str(img.width).encode("ascii") +
            b" /Height " + str(img.height).encode("ascii") +
            b" /ColorSpace " + colorspace +
            b" /BitsPerComponent 8 /Filter /FlateDecode" + decode_parms +
            b" /Length " + str(len(img.flate_data)).encode("ascii") + b" >>\nstream\n" +
            img.flate_data + b"\nendstream"
        )
        img_content = f"q {img.width} 0 0 {img.height} 0 0 cm /Im0 Do Q".encode("ascii")
        img_content_id = add_object(
            b"<< /Length " + str(len(img_content)).encode("ascii") + b" >>\nstream\n" +
            img_content + b"\nendstream"
        )
        kids.append(add_object(
            b"<< /Type /Page /Parent " + str(pages_id).encode("ascii") + b" 0 R "
            b"/MediaBox [0 0 " + str(img.width).encode("ascii") + b" " +
            str(img.height).encode("ascii") + b"] "
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


def _assemble(objects: List[bytes], catalog_id: int) -> bytes:
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
