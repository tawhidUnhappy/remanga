"""Builds the PDF variant of the LLM upload bundle - see
remanga.cropper.llm_zip's module docstring for the zip variant this mirrors
closely (same LLMBundleConfig.max_mb/pdf_split_enabled behavior, same
lossless-or-nothing guarantee, same per-part chapter identity); this is the
PDF equivalent for chat interfaces that handle a single PDF upload more
gracefully than a zip of individual images. Off by default, unlike the zip
(LLMBundleConfig) - PDF is a less universally-supported upload format, and
has no dedicated lossless image codec of its own to lean on (see below).
Written to panels_pdf/panels_1.pdf, panels_2.pdf, ... - never touches
panels/ itself or the primary vision archive.

See remanga.cropper.pdf_writer's module docstring for why this doesn't just
use Pillow's own `Image.save(..., "PDF")` (short version: it's lossy for RGB
images, with no way to turn that off short of quantizing to a 256-color
palette).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import numpy as np

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.image_codec import open_normalized
from remanga.cropper.pdf_writer import (
    ImagePage,
    build_pdf,
    decode_flate_raw,
    decode_predictor2,
    encode_flate_raw,
    encode_predictor2,
)
from remanga.cropper.size_pack import pack_by_size
from remanga.paths import chapter_identity_fields


def _encode_panel(path: Path) -> ImagePage:
    """Encodes one panel as a lossless PDF image page, verifying the round
    trip before returning anything. Tries TIFF-Predictor-2 first (usually
    ~15-20% smaller); if that somehow doesn't verify, falls back to plain
    raw+flate (no predictor - simpler, nothing left to get wrong beyond zlib
    itself) and verifies that too. Raises only if neither round-trips, which
    would mean something is very wrong with this specific image."""
    img = open_normalized(path)
    if img.mode == "RGBA":
        # PDF's DeviceRGB colorspace has no alpha component; every real panel
        # crop.py produces is already plain RGB, so this only ever matters for
        # some other file that ended up in panels_dir.
        img = img.convert("RGB")

    arr = np.asarray(img)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    colors = arr.shape[2]

    flate_data = encode_predictor2(arr)
    if np.array_equal(decode_predictor2(flate_data, arr.shape), arr):
        return ImagePage(width=img.width, height=img.height, flate_data=flate_data, colors=colors, predictor=2)

    flate_data = encode_flate_raw(arr)
    if np.array_equal(decode_flate_raw(flate_data, arr.shape), arr):
        return ImagePage(width=img.width, height=img.height, flate_data=flate_data, colors=colors, predictor=None)

    raise ValueError(f"neither predictor2 nor raw flate round-tripped exactly for {path.name}")


def build_llm_pdf_bundle(
    config: CropperConfig,
    chapter_dir: Path,
    project_name: str,
    chapter_num: str,
    panel_paths: List[Path],
) -> List[Path]:
    """Builds panels_pdf/panels_1.pdf, panels_2.pdf, ... - see module
    docstring. A no-op returning [] if disabled or there are no panels.
    Clears out any stale parts from a previous run first. If any single panel
    can't be losslessly encoded (see _encode_panel - practically never, but
    never say never), the whole bundle is aborted rather than shipped
    missing a panel: a partial PDF silently under-representing the chapter is
    worse than no PDF at all, and the primary archive/zip bundle remain
    available regardless."""
    out_dir = chapter_dir / "panels_pdf"
    if not config.llm_bundle.pdf_active or not panel_paths:
        if out_dir.exists():
            for stale in out_dir.glob("panels_*.pdf"):
                stale.unlink()
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("panels_*.pdf"):
        stale.unlink()

    max_bytes = max(1, int(config.llm_bundle.max_mb * 1024 * 1024))

    encoded: List[Tuple[str, ImagePage]] = []
    for path in sorted(panel_paths):
        try:
            page = _encode_panel(path)
        except Exception as e:
            console.print(
                f"[bold red]✗ LLM PDF bundle aborted:[/] {path.name} couldn't be losslessly "
                f"encoded ({e}) - the zip bundle/primary archive are unaffected."
            )
            for partial in out_dir.glob("panels_*.pdf"):
                partial.unlink()
            return []
        encoded.append((path.stem, page))

    parts = pack_by_size(encoded, lambda item: len(item[1].flate_data), max_bytes, config.llm_bundle.pdf_split_enabled)

    total_parts = len(parts)
    identity = chapter_identity_fields(project_name, chapter_num)
    written: List[Path] = []
    for idx, part in enumerate(parts, start=1):
        info = dict(identity)
        info["part_index"] = idx
        info["total_parts"] = total_parts
        info["panel_id_start"] = part[0][0]
        info["panel_id_end"] = part[-1][0]
        info_lines = [f"{k}: {v}" for k, v in info.items()]

        pdf_bytes = build_pdf([page for _, page in part], info_lines)
        pdf_path = out_dir / f"panels_{idx}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        written.append(pdf_path)

    # Unlike the zip bundle's PNG/WEBP re-encoding, embedding raw (Flate/
    # predictor-compressed) bitmaps in a PDF isn't reliably smaller than the
    # source panel files - PDF has no dedicated image codec of its own, so
    # this reports the resulting size plainly rather than claiming a "saved"
    # figure that would sometimes be negative.
    total_mb = sum(p.stat().st_size for p in written) / (1024 * 1024)
    size_note = f"{total_parts} part(s), ≤{config.llm_bundle.max_mb:g}MB each" if config.llm_bundle.pdf_split_enabled \
        else "1 part, splitting off"
    console.print(
        f"[bold green]✓ Built LLM upload bundle - PDF ({size_note}, {total_mb:.1f}MB total) in:[/] {out_dir}"
    )
    return written
