"""Builds the manifest/info section bundled into every LLM upload format
(panels_zip, sheets_zip, pdf/pdf_splite/pdf_zip/pdf_zip_splite, and the grid
formats of the LLM crop workflow) - a plain ordered list of every item name
the *whole* format contains (`full_manifest`), plus which of those this
specific part actually holds (`contents`), so the LLM (or the user) can spot
anything missing just by comparing the two lists, without depending on anyone
counting panels by hand.

Shared by:
- remanga.cropper.zip_bundle (panels_zip/sheets_zip/grid_zip) - embedded as
  chapter_info.json inside the zip.
- remanga.cropper.llm_pdf (pdf/pdf_splite/pdf_zip/pdf_zip_splite, grid_pdf...)
  - rendered as the PDF's own leading text page(s) via `info_to_text_lines`,
  and also embedded as chapter_info.json for the zipped variants.
- remanga.cropper.sheets (the sheets_zip/sheets info sheet, and grid_pages'
  000_info image) - rendered as an image via `info_to_text_lines`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_part_info(
    identity: dict[str, Any],
    full_ids: Sequence[str],
    part_ids: Sequence[str],
    part_index: int,
    total_parts: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One part's chapter_info.json payload - `identity` is
    remanga.paths.chapter_identity_fields' project/manga/chapter dict,
    `full_ids` is every item name in this format across every part, in
    order, and `part_ids` is just the ones actually in this part. `extra` is
    whatever a format adds for its reader (the grid formats' grouping, grid
    spec and page areas), placed right after the identity."""
    info = dict(identity)
    info.update(extra or {})
    info["part_index"] = part_index
    info["total_parts"] = total_parts
    info["total_items"] = len(full_ids)
    info["contents"] = list(part_ids)
    info["full_manifest"] = list(full_ids)
    return info


def info_to_text_lines(info: dict[str, Any]) -> list[str]:
    """Renders a build_part_info() dict as plain lines of text - used for
    the PDF formats' leading info page(s) and the sheets formats' info
    sheet. List-valued keys (`contents`/`full_manifest`) get their own
    labeled section instead of being dumped inline, and a dict-valued key
    gets one indented line per entry rather than one line too long for a
    page."""
    lines = []
    for k, v in info.items():
        if isinstance(v, list):
            continue
        if isinstance(v, dict):
            lines.append(f"{k}:")
            lines.extend(f"  {sub_key}: {sub_value}" for sub_key, sub_value in v.items())
            continue
        lines.append(f"{k}: {v}")

    contents = info.get("contents", [])
    lines.append("")
    lines.append(f"Contents of this part ({len(contents)} item(s)):")
    lines.extend(contents)

    full_manifest = info.get("full_manifest", [])
    if full_manifest != contents:
        lines.append("")
        lines.append(
            f"Full chapter manifest ({len(full_manifest)} item(s) total across every part - "
            f"compare against this to spot anything missing):"
        )
        lines.extend(full_manifest)

    return lines
