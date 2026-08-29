"""Builds the zip variant of the size-capped LLM upload bundle - a second
vision archive purely for uploading to an LLM chat interface, many of which
cap file uploads well under what a full chapter's full-resolution panel PNGs
add up to (a single chapter easily runs 50-100+ MB). Completely separate from:
- panels/ itself, which is untouched and stays the full-quality source video
  rendering reads from (remanga.video.compose) - this module only ever READS
  those files, never writes into that folder.
- the primary vision archive (remanga.cropper.archive's sheets.zip/panels.zip),
  which keeps working exactly as it did before this module existed - the
  "previous legacy method" prompts/narration.md still documents alongside this
  one (and alongside remanga.cropper.llm_pdf, the PDF equivalent). It now
  shares this module's own lossless-shrink step (image_codec.py), just packed
  into a single, unsplit zip instead of size-capped parts.

Strategy, in order:
1. Shrink each panel losslessly via remanga.cropper.image_codec's
   smallest_lossless_encoding - no pixel is altered, ever; see that module for
   how the "lossless" claim is actually verified rather than assumed.
2. Pack the (still full-quality) shrunk images into as many zip parts as
   needed to keep each part at or under `LLMBundleConfig.max_mb`
   (remanga.cropper.size_pack.pack_by_size), splitting only on panel
   boundaries (in original reading order) so a part is never larger than the
   cap unless a single panel alone already exceeds it.

Each part gets its own chapter_info.json (same identity fields as the primary
archive's - see remanga.paths.chapter_identity_fields - plus part_index/
total_parts/panel_id_start/panel_id_end) so the LLM can place a part and know
how many others to expect without depending on the filename at all.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import List, Tuple

from remanga.config import CropperConfig
from remanga.console import console
from remanga.cropper.image_codec import smallest_lossless_encoding
from remanga.cropper.size_pack import pack_by_size
from remanga.paths import chapter_identity_fields


def build_llm_zip_bundle(
    config: CropperConfig,
    chapter_dir: Path,
    project_name: str,
    chapter_num: str,
    panel_paths: List[Path],
) -> List[Path]:
    """Builds panels_zip/panels_1.zip, panels_2.zip, ... - see module docstring.
    A no-op returning [] if disabled or there are no panels. Clears out any
    stale parts from a previous run before writing the current ones, so a
    chapter that now needs fewer parts doesn't leave old extras behind."""
    out_dir = chapter_dir / "panels_zip"
    if not config.llm_bundle.zip_enabled or not panel_paths:
        if out_dir.exists():
            for stale in out_dir.glob("panels_*.zip"):
                stale.unlink()
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("panels_*.zip"):
        stale.unlink()

    max_bytes = max(1, int(config.llm_bundle.max_mb * 1024 * 1024))

    encoded: List[Tuple[str, str, bytes]] = []  # (panel_id, arcname, data)
    original_total = 0
    for path in sorted(panel_paths):
        data, ext = smallest_lossless_encoding(path)
        original_total += path.stat().st_size
        encoded.append((path.stem, f"{path.stem}{ext}", data))

    parts = pack_by_size(encoded, lambda item: len(item[2]), max_bytes)

    total_parts = len(parts)
    identity = chapter_identity_fields(project_name, chapter_num)
    written: List[Path] = []
    for idx, part in enumerate(parts, start=1):
        zip_path = out_dir / f"panels_{idx}.zip"
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
    console.print(
        f"[bold green]✓ Built LLM upload bundle - ZIP ({total_parts} part(s), "
        f"≤{config.llm_bundle.max_mb:g}MB each) in:[/] {out_dir} "
        f"[dim](losslessly saved {saved_mb:.1f}MB re-encoding panels)[/]"
    )
    return written
