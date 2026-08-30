"""Shared, format-agnostic image helpers used everywhere a panel image gets
losslessly shrunk or embedded elsewhere: the panels_zip/sheets_zip bundles
(remanga.cropper.zip_bundle, remanga.cropper.sheets), and - for the
underlying open/verify primitives - the panels_pdf bundle (remanga.cropper.
llm_pdf's own raw FlateDecode re-encoding). One place for opening/normalizing
a panel image the same way every caller starts from, and for the one thing
that actually makes any of their "lossless" claims trustworthy - decoding a
candidate re-encoding back and comparing it pixel-for-pixel against the
source, rather than trusting a codec's own lossless flag (or our own filter
math) blindly.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Tuple

from PIL import Image


def open_normalized(path: Path) -> Image.Image:
    """Opens a panel image and returns it in RGB or RGBA mode - the only modes
    the encoders below need to handle. Every panel crop.py produces is
    already RGB, so this is a no-op for the common case and just a safety net
    for anything else that ever ends up in panels_dir."""
    img = Image.open(path)
    img.load()
    return img if img.mode in ("RGB", "RGBA") else img.convert("RGB")


def pixel_identical(reference: Image.Image, candidate_bytes: bytes) -> bool:
    """True if decoding `candidate_bytes` (any file format Pillow can open)
    gives back exactly `reference`'s pixels - same size, same mode once
    aligned, same bytes. Any exception decoding the candidate counts as "not
    identical" rather than propagating, so a caller can just treat this as a
    plain pass/fail check."""
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


def smallest_lossless_encoding_for_image(img: Image.Image, best_bytes: bytes = b"", best_ext: str = ".png") -> Tuple[bytes, str]:
    """The actual codec comparison behind `smallest_lossless_encoding` below,
    factored out so it can also run on an image that only exists in memory -
    a composited sheet canvas (remanga.cropper.sheets), not a file on disk.

    Tries a re-optimized PNG and a lossless WEBP, keeping whichever - either
    of those two, or whatever was passed in as the starting `best_bytes`/
    `best_ext` - comes out smallest, and only if `pixel_identical` confirms
    it decodes back to the exact same pixels first. Pass no starting
    baseline (the defaults) to just compare the two candidates against each
    other, which is what a from-scratch composited image needs, since
    there's no pre-existing file to also consider."""
    try:
        src = img if img.mode in ("RGB", "RGBA") else img.convert("RGB")

        png_buf = io.BytesIO()
        src.save(png_buf, "PNG", optimize=True, compress_level=9)
        png_bytes = png_buf.getvalue()
        if (not best_bytes or len(png_bytes) < len(best_bytes)) and pixel_identical(src, png_bytes):
            best_bytes, best_ext = png_bytes, ".png"

        # method=6 (max effort) was benchmarked at ~25x method=4's encode
        # time for only ~3% extra size reduction on manga panel art -
        # nowhere near worth it when this runs on every panel of every
        # chapter cropped. method=4 gets nearly all of the size win at a
        # small fraction of the cost; lossless=True is what guarantees no
        # quality loss either way, not the method number.
        webp_buf = io.BytesIO()
        src.save(webp_buf, "WEBP", lossless=True, quality=100, method=4)
        webp_bytes = webp_buf.getvalue()
        if (not best_bytes or len(webp_bytes) < len(best_bytes)) and pixel_identical(src, webp_bytes):
            best_bytes, best_ext = webp_bytes, ".webp"
    except Exception:
        pass

    return best_bytes, best_ext


def smallest_lossless_encoding(path: Path) -> Tuple[bytes, str]:
    """Returns (bytes, extension) for whichever lossless encoding of this
    panel image comes out smallest: the original file as-is, a re-optimized
    PNG, or a lossless WEBP - each of the latter two only wins if
    `pixel_identical` actually confirms it decodes back to the exact same
    image. Never touches `path` itself; the caller decides where (or
    whether) the result gets written.

    Shared by every zip-based archive that packs panel images - the primary
    vision archive (archive.py) and the LLM zip bundle (llm_zip.py) alike -
    so the same storage-optimizing, quality-preserving encode only has to be
    implemented, and trusted, once."""
    original_bytes = path.read_bytes()
    original_ext = path.suffix.lower() or ".png"

    try:
        with Image.open(path) as img:
            img.load()
            return smallest_lossless_encoding_for_image(img, original_bytes, original_ext)
    except Exception:
        # Any decode/encode hiccup on this one image: ship the original file
        # untouched rather than let an optimization attempt block the batch.
        return original_bytes, original_ext
