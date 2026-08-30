"""Generic size-capped zip-bundle builder, shared by every LLM-upload zip
format that only differs in *which* images it packages and where -
remanga.cropper.llm_zip (individual panel crops) and remanga.cropper.
llm_sheets (2x2 contact sheet composites). One implementation of "shrink
losslessly, then pack into one file or split into size-capped parts" instead
of a near-duplicate copy per format.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import List, Tuple

from remanga.console import console
from remanga.cropper.image_codec import smallest_lossless_encoding
from remanga.cropper.size_pack import pack_by_size
from remanga.paths import chapter_identity_fields


def build_zip_bundle(
    image_paths: List[Path],
    out_dir: Path,
    file_prefix: str,
    enabled: bool,
    split_enabled: bool,
    max_mb: float,
    project_name: str,
    chapter_num: str,
    label: str,
) -> List[Path]:
    """Builds `out_dir`/`file_prefix`_1.zip, `file_prefix`_2.zip, ... from
    `image_paths` (already-produced images - individual panels or sheet
    composites, whichever the caller passes). A no-op returning [] if
    neither `enabled` nor `split_enabled` is set (see PackageConfig's
    docstring for what that pair means together) or there are no images.
    Clears out any stale parts from a previous run first, so a chapter that
    now needs fewer parts doesn't leave old extras behind.

    Every image is re-encoded losslessly first (image_codec.
    smallest_lossless_encoding - no pixel ever altered), then packed into
    one single zip (the default) or split into `max_mb`-capped parts if
    `split_enabled` is on (size_pack.pack_by_size). `label` is only used for
    the console summary line (e.g. "ZIP" or "SHEETS ZIP")."""
    active = enabled or split_enabled
    if not active or not image_paths:
        if out_dir.exists():
            for stale in out_dir.glob(f"{file_prefix}_*.zip"):
                stale.unlink()
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"{file_prefix}_*.zip"):
        stale.unlink()

    max_bytes = max(1, int(max_mb * 1024 * 1024))

    encoded: List[Tuple[str, str, bytes]] = []  # (item_id, arcname, data)
    original_total = 0
    for path in sorted(image_paths):
        data, ext = smallest_lossless_encoding(path)
        original_total += path.stat().st_size
        encoded.append((path.stem, f"{path.stem}{ext}", data))

    parts = pack_by_size(encoded, lambda item: len(item[2]), max_bytes, split_enabled)

    total_parts = len(parts)
    identity = chapter_identity_fields(project_name, chapter_num)
    written: List[Path] = []
    for idx, part in enumerate(parts, start=1):
        zip_path = out_dir / f"{file_prefix}_{idx}.zip"
        info = dict(identity)
        info["part_index"] = idx
        info["total_parts"] = total_parts
        info["panel_id_start"] = part[0][0]
        info["panel_id_end"] = part[-1][0]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for _, arcname, data in part:
                zf.writestr(arcname, data)
            zf.writestr("chapter_info.json", json.dumps(info, indent=2) + "\n")
        written.append(zip_path)

    encoded_total = sum(len(data) for _, _, data in encoded)
    saved_mb = max(0, original_total - encoded_total) / (1024 * 1024)
    size_note = f"{total_parts} part(s), ≤{max_mb:g}MB each" if split_enabled \
        else f"1 part, {encoded_total / (1024 * 1024):.1f}MB, splitting off"
    console.print(
        f"[bold green]✓ Built LLM upload bundle - {label} ({size_note}) in:[/] {out_dir} "
        f"[dim](losslessly saved {saved_mb:.1f}MB re-encoding)[/]"
    )
    return written
