"""Builds the panels_pdf package format - see remanga.cropper.llm_zip's
module docstring for the zip format this mirrors closely (same
PackageConfig.max_mb behavior, same lossless-or-nothing guarantee, same
per-part chapter identity); this is the PDF equivalent for chat interfaces
that handle a single PDF upload more gracefully than a zip of individual
images. Off by default, unlike panels_zip - PDF is a less
universally-supported upload format, and has no dedicated lossless image
codec of its own to lean on (see below).

Four independent switches (see PackageConfig), all coordinated here:
- `pdf` - a single panels_1.pdf, unsplit.
- `pdf_splite` - the PDF split into `max_mb`-capped raw .pdf files instead,
  not zipped: panels_1.pdf, panels_2.pdf, ....
- `pdf_zip` - the single PDF, wrapped in panels_1.zip.
- `pdf_zip_splite` - the PDF split into `max_mb`-capped parts, each zipped
  separately: panels_1.zip, panels_2.zip, ....

Written to panels_pdf/ - never touches panels/ itself.

The builder itself, `build_pdf_bundle`, takes those four switches as plain
arguments, so the LLM crop workflow's grid_pdf formats (LLMCropConfig, the
same four switches over gridded pages - see remanga.cropper.grid_bundles)
are built by exactly this code too.

See remanga.cropper.pdf_writer's module docstring for why this doesn't just
use Pillow's own `Image.save(..., "PDF")` (short version: it's lossy for RGB
images, with no way to turn that off short of quantizing to a 256-color
palette).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.cropper.image_codec import open_normalized
from remanga.cropper.manifest_info import build_part_info, info_to_text_lines
from remanga.cropper.pdf_writer import (
    ImagePage,
    build_pdf,
    decode_flate_raw,
    decode_predictor2,
    encode_flate_raw,
    encode_predictor2,
)
from remanga.cropper.size_pack import pack_by_size
from remanga.paths import chapter_identity_fields, get_panels_pdf_dir


def _encode_image(path: Path) -> ImagePage:
    """Encodes one image as a lossless PDF image page, verifying the round
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


def _clear(out_dir: Path, file_prefix: str) -> None:
    for stale in out_dir.glob(f"{file_prefix}_*.pdf"):
        stale.unlink()
    for stale in out_dir.glob(f"{file_prefix}_*.zip"):
        stale.unlink()


def build_pdf_bundle(
    image_paths: list[Path],
    out_dir: Path,
    file_prefix: str,
    single: bool,
    split: bool,
    zipped: bool,
    zipped_split: bool,
    max_mb: float,
    project_name: str,
    chapter_num: str,
    label: str,
    extra_info: dict[str, Any] | None = None,
) -> list[Path]:
    """Builds `out_dir`/`file_prefix`_1.pdf, _2.pdf, ... (and/or the zipped
    .zip parts) from `image_paths`. The four switches mean what PackageConfig's
    pdf/pdf_splite/pdf_zip/pdf_zip_splite mean. A no-op returning [] if none
    is on or there are no images. Clears out any stale parts from a previous
    run first. If any single image can't be losslessly encoded (see
    _encode_image - practically never, but never say never), the whole
    bundle is aborted rather than shipped missing an image: a partial PDF
    silently under-representing the chapter is worse than no PDF at all.
    `extra_info` is added to every part's info (see manifest_info.
    build_part_info)."""
    if not (single or split or zipped or zipped_split) or not image_paths:
        if out_dir.exists():
            _clear(out_dir, file_prefix)
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    _clear(out_dir, file_prefix)

    max_bytes = max(1, int(max_mb * 1024 * 1024))

    encoded: list[tuple[str, ImagePage]] = []
    for path in sorted(image_paths):
        try:
            page = _encode_image(path)
        except Exception as e:
            console.print(
                f"[bold red]✗ LLM {label} bundle aborted:[/] {path.name} couldn't be losslessly "
                f"encoded ({e}) - the other upload formats are unaffected."
            )
            _clear(out_dir, file_prefix)
            return []
        encoded.append((path.stem, page))

    split_parts = split or zipped_split
    parts = pack_by_size(encoded, lambda item: len(item[1].flate_data), max_bytes, split_parts)

    total_parts = len(parts)
    identity = chapter_identity_fields(project_name, chapter_num)
    full_ids = [item_id for item_id, _ in encoded]
    written: list[Path] = []
    for idx, part in enumerate(parts, start=1):
        part_ids = [item_id for item_id, _ in part]
        info = build_part_info(identity, full_ids, part_ids, idx, total_parts, extra=extra_info)
        info_lines = info_to_text_lines(info)

        pdf_bytes = build_pdf([page for _, page in part], info_lines)
        pdf_name = f"{file_prefix}_{idx}.pdf"

        if single or split:
            pdf_path = out_dir / pdf_name
            pdf_path.write_bytes(pdf_bytes)
            written.append(pdf_path)

        if zipped or zipped_split:
            zip_path = out_dir / f"{file_prefix}_{idx}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                zf.writestr(pdf_name, pdf_bytes)
                zf.writestr("chapter_info.json", json.dumps(info, indent=2) + "\n")
            written.append(zip_path)

    # Unlike the zip bundle's PNG/WEBP re-encoding, embedding raw (Flate/
    # predictor-compressed) bitmaps in a PDF isn't reliably smaller than the
    # source image files - PDF has no dedicated image codec of its own, so
    # this reports the resulting size plainly rather than claiming a "saved"
    # figure that would sometimes be negative.
    total_mb = sum(p.stat().st_size for p in written) / (1024 * 1024)
    size_note = f"{total_parts} part(s), ≤{max_mb:g}MB each" if split_parts else "1 part, splitting off"
    console.print(
        f"[bold green]✓ Built LLM upload bundle - {label} ({size_note}, {total_mb:.1f}MB total) in:[/] "
        f"{_esc(str(out_dir))}"
    )
    return written


def build_llm_pdf_bundle(
    config: CropperConfig,
    project_name: str,
    chapter_num: str,
    panel_paths: list[Path],
) -> list[Path]:
    """Builds panels_pdf/panels_1.pdf, panels_2.pdf, ... - see module
    docstring."""
    package = config.package
    return build_pdf_bundle(
        panel_paths, get_panels_pdf_dir(project_name, chapter_num, create=False), "panels",
        package.pdf, package.pdf_splite, package.pdf_zip, package.pdf_zip_splite, package.max_mb,
        project_name, chapter_num, "PDF",
    )
