"""Shared, format-agnostic image helpers for the LLM upload bundles
(remanga.cropper.llm_zip's PNG/WEBP re-encoding, remanga.cropper.llm_pdf's raw
FlateDecode re-encoding): opening/normalizing a panel image the same way both
start from, and the one thing that actually makes either bundle's "lossless"
claim trustworthy - decoding a candidate re-encoding back and comparing it
pixel-for-pixel against the source, rather than trusting a codec's own
lossless flag (or our own filter math) blindly.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


def open_normalized(path: Path) -> Image.Image:
    """Opens a panel image and returns it in RGB or RGBA mode - the only modes
    the bundle encoders need to handle. Every panel crop.py produces is
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
