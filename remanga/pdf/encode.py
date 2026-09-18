"""Turning one panel image into a PDF page, as small as it can be without
changing it.

A JPEG panel is embedded as its own bytes - the file exactly as it was cut,
and smaller than any re-encoding of its pixels. Anything else goes in as the
smaller of two verified lossless encodings (PNG row filters, or TIFF
Predictor 2), one channel instead of three when it is pure grayscale. Every
one of those is checked against the source pixels before it is used.

`near_lossless_pages` is the fallback for a single panel too big to fit in a
part on its own: the smallest no-dither palette or 4:4:4 JPEG that still
reaches each PSNR floor, best first."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from remanga.pdf.writer import (
    ImagePage,
    PngStream,
    decode_predictor2,
    encode_predictor2,
    png_idat_stream,
)

# The quality floors a panel may step down through, best first, when its PDF
# would otherwise go over the cap - PSNR in dB against the panel's own
# pixels. At 45 the difference is invisible side by side; 36 is the floor,
# below which a panel is better off in a split PDF than degraded further.
PSNR_FLOORS = (45.0, 42.0, 39.0, 36.0)
_PALETTE_SIZES = (256, 128, 64, 32, 16)
_JPEG_QUALITIES = (95, 92, 88, 85, 80)


def _load_array(path: Path) -> tuple[Image.Image, np.ndarray]:
    """The image as RGB or L, and its pixels. A page whose three channels are
    identical everywhere is returned as L - the same pixels exactly, a third
    of the data."""
    img = open_normalized(path)
    if img.mode == "RGBA":
        # PDF's DeviceRGB has no alpha.
        img = img.convert("RGB")
    arr = np.asarray(img)
    if arr.ndim == 3 and np.array_equal(arr[:, :, 0], arr[:, :, 1]) and np.array_equal(arr[:, :, 1], arr[:, :, 2]):
        img = img.convert("L")
        arr = np.asarray(img)
    return img, arr


def _psnr(original: np.ndarray, other: Image.Image, mode: str) -> float:
    back = np.asarray(other.convert(mode), dtype=np.float32)
    mse = float(np.mean((back - original.astype(np.float32)) ** 2))
    return float("inf") if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def _png_page(stream: PngStream, lossless: bool) -> ImagePage:
    return ImagePage(stream.width, stream.height, stream.data, colors=stream.colors, predictor=15,
                     palette=stream.palette, bits=stream.bits, lossless=lossless)


def _jpeg_passthrough(path: Path) -> ImagePage | None:
    """The file itself as a DCTDecode page, when it is a grayscale or RGB
    JPEG with no EXIF rotation (which a PDF reader would not apply)."""
    try:
        with Image.open(path) as img:
            if img.format != "JPEG" or img.mode not in ("L", "RGB"):
                return None
            if img.getexif().get(0x0112, 1) != 1:
                return None
            width, height, colors = img.width, img.height, 1 if img.mode == "L" else 3
    except OSError:
        return None
    return ImagePage(width, height, path.read_bytes(), colors=colors, predictor=None, filter="DCTDecode")


def lossless_page(path: Path) -> ImagePage:
    """The smallest lossless PDF page for this image, verified before it is
    trusted: PNG's per-row filters (taken from a PNG Pillow wrote, which it
    must decode back to identical pixels) or TIFF Predictor 2 (decoded back
    here). Raises only if neither round-trips."""
    img, arr = _load_array(path)
    colors = 1 if arr.ndim == 2 else 3
    candidates: list[ImagePage] = []

    # A JPEG source goes in as its own bytes: the page then holds exactly the
    # file it came from, where re-encoding its decoded pixels losslessly would
    # be several times the size (a downloaded chapter's pages, typically).
    source = _jpeg_passthrough(path)
    if source is not None:
        candidates.append(source)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    png = buf.getvalue()
    if pixel_identical(img, png):
        stream = png_idat_stream(png)
        if (stream.width, stream.height, stream.colors, stream.palette) == (img.width, img.height, colors, None):
            candidates.append(_png_page(stream, lossless=True))

    shaped = arr if arr.ndim == 3 else arr[:, :, None]
    data = encode_predictor2(shaped)
    if np.array_equal(decode_predictor2(data, shaped.shape), shaped):
        candidates.append(ImagePage(img.width, img.height, data, colors=colors, predictor=2))

    if not candidates:
        raise ValueError(f"no lossless encoding round-tripped exactly for {path.name}")
    return min(candidates, key=lambda page: len(page.data))


def near_lossless_pages(path: Path) -> list[tuple[ImagePage, float]]:
    """Every near-lossless page this image has, each with its PSNR against
    the original: palette versions (quantized without dithering, so line
    art stays crisp) and JPEG versions (no chroma subsampling). A candidate
    that fails to encode is left out."""
    img, arr = _load_array(path)
    out: list[tuple[ImagePage, float]] = []
    rgb = img.convert("RGB")
    for size in _PALETTE_SIZES:
        try:
            quantized = rgb.quantize(size, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            buf = io.BytesIO()
            quantized.save(buf, "PNG", optimize=True)
            out.append((_png_page(png_idat_stream(buf.getvalue()), lossless=False),
                        _psnr(arr, quantized, img.mode)))
        except (ValueError, OSError):
            continue
    colors = 1 if img.mode == "L" else 3
    for quality in _JPEG_QUALITIES:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, subsampling=0, optimize=True)
        data = buf.getvalue()
        with Image.open(io.BytesIO(data)) as decoded:
            psnr = _psnr(arr, decoded, img.mode)
        out.append((ImagePage(img.width, img.height, data, colors=colors, predictor=None,
                              filter="DCTDecode", lossless=False), psnr))
    return out


def open_normalized(path: Path) -> Image.Image:
    """An image in RGB or RGBA mode, loaded."""
    img = Image.open(path)
    img.load()
    return img if img.mode in ("RGB", "RGBA") else img.convert("RGB")


def pixel_identical(reference: Image.Image, candidate_bytes: bytes) -> bool:
    """Whether `candidate_bytes` decodes back to exactly `reference`'s pixels."""
    try:
        with Image.open(io.BytesIO(candidate_bytes)) as decoded:
            decoded.load()
            if decoded.size != reference.size:
                return False
            if decoded.mode != reference.mode:
                decoded = decoded.convert(reference.mode)
            return decoded.tobytes() == reference.tobytes()
    except Exception:
        return False
