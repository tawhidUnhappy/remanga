"""How an image goes into the PDF losslessly: a PNG's own IDAT data (it IS a
PDF FlateDecode stream with /Predictor 15, byte for byte), TIFF Predictor 2,
or raw Flate - and the decoders that check a page round-trips. See writer.py
for why this is built by hand rather than with Pillow's PDF writer."""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np


@dataclass
class PngStream:
    width: int
    height: int
    colors: int
    bits: int
    palette: bytes | None
    data: bytes


def png_idat_stream(png: bytes) -> PngStream:
    """The image data of a non-interlaced 8-bit grayscale or RGB PNG, or a
    palette PNG of any bit depth: its IDAT chunks joined, which PDF reads as
    FlateDecode with /Predictor 15 (PNG filters, chosen per row) - the same
    trick img2pdf uses - plus the palette. Raises ValueError for any other
    kind of PNG."""
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, header, palette = 8, bytearray(), None, None
    while pos < len(png):
        length = int.from_bytes(png[pos:pos + 4], "big")
        kind = png[pos + 4:pos + 8]
        body = png[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"PLTE":
            palette = bytes(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if header is None or not idat:
        raise ValueError("PNG has no IHDR or IDAT")
    width, height = int.from_bytes(header[0:4], "big"), int.from_bytes(header[4:8], "big")
    depth, color_type, interlace = header[8], header[9], header[12]
    colors = {0: 1, 2: 3, 3: 1}.get(color_type)
    indexed = color_type == 3
    if colors is None or interlace != 0 or (depth != 8 and not indexed) or (indexed and not palette):
        raise ValueError(f"unsupported PNG (depth {depth}, color type {color_type}, interlace {interlace})")
    return PngStream(width, height, colors, depth, palette if indexed else None, bytes(idat))


def encode_predictor2(arr: np.ndarray) -> bytes:
    """TIFF Predictor 2 (per-row, per-component horizontal differencing,
    matching the PDF/TIFF6 spec exactly) then zlib - PDF's own native
    lossless image representation, and what `ImagePage.data` should
    hold when `predictor=2`. `arr` is (H, W, colors) uint8. Any standards-
    compliant PDF reader decodes this back exactly; `decode_predictor2`
    (below) implements the same inverse purely so a caller can self-verify a
    round-trip before trusting the encoded bytes (see builder.py)."""
    diff = arr.copy()
    diff[:, 1:, :] = arr[:, 1:, :] - arr[:, :-1, :]
    return zlib.compress(diff.astype(np.uint8).tobytes(), 9)


def decode_predictor2(flate_data: bytes, shape: tuple[int, int, int]) -> np.ndarray:
    """Inverse of encode_predictor2 - decompresses and reverses the
    per-row horizontal differencing via a cumulative sum (mod 256) along the
    column axis, which telescopes back to the original values exactly."""
    diff = np.frombuffer(zlib.decompress(flate_data), dtype=np.uint8).reshape(shape)
    return (np.cumsum(diff.astype(np.int32), axis=1) % 256).astype(np.uint8)


def encode_flate_raw(arr: np.ndarray) -> bytes:
    """Plain zlib over the raw bitmap, no predictor - a simpler, strictly more
    robust fallback `ImagePage(..., predictor=None)` can use if
    encode_predictor2 ever fails to round-trip (see builder.py). Produces a
    noticeably larger stream (no horizontal decorrelation), but every step is
    just zlib, nothing left to get subtly wrong."""
    return zlib.compress(arr.astype(np.uint8).tobytes(), 9)


def decode_flate_raw(flate_data: bytes, shape: tuple[int, int, int]) -> np.ndarray:
    return np.frombuffer(zlib.decompress(flate_data), dtype=np.uint8).reshape(shape)
