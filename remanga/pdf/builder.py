"""A chapter's panels as PDF files for the LLM, never over the size cap.

Two steps, each in its own module: every panel is encoded losslessly
(encode.py), then the panels are packed into as many parts as the cap needs
(pack.py). Each part starts with a text page - the chapter's identity,
reading direction, which panels this part holds, the chapter's full panel
list, and the story so far (manifest_info.py).

Why not Pillow's own PDF writer: it re-encodes every image as JPEG, with no
way to turn that off (see writer.py)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from remanga.console import console, escape as _esc
from remanga.pdf.encode import PSNR_FLOORS, lossless_page
from remanga.pdf.manifest_info import build_part_info, info_to_text_lines
from remanga.pdf.pack import _Built, _pack_parts, _Page, _quality_note
from remanga.pdf.writer import build_pdf

_WORKERS = min(8, os.cpu_count() or 1)


def build_panels_pdf(
    image_paths: list[Path],
    out_dir: Path,
    max_mb: float,
    info: dict[str, Any],
) -> list[Path]:
    """Writes `out_dir`/panels_1.pdf, panels_2.pdf, ... from `image_paths`,
    each at most `max_mb`, replacing any parts from an earlier build. `info`
    is the chapter's identity and anything else the text page should carry.
    Returns the parts written; raises when a panel can't be encoded or can't
    fit under the cap."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("p*_*.pdf"):  # panels_*.pdf, and any pages_*.pdf from before
        stale.unlink()
    max_bytes = max(1, int(max_mb * 1024 * 1024))

    paths = list(image_paths)
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        lossless = list(pool.map(lossless_page, paths))
    pages = [_Page(path.stem, path, page) for path, page in zip(paths, lossless, strict=True)]
    full_ids = [page.stem for page in pages]
    # Every page of every part is the size of the chapter's biggest panel,
    # with the panel centred on black: panels are all different shapes, and a
    # PDF that changes shape on every scroll is hard to read.
    canvas = (max(page.page.width for page in pages), max(page.page.height for page in pages))

    def render(part: Sequence[_Page], index: int, total: int) -> _Built:
        part_info = build_part_info(info, full_ids, [page.stem for page in part], index, total)
        return _Built(build_pdf([page.page for page in part], info_to_text_lines(part_info), canvas))

    built = _pack_parts(pages, max_bytes, render)
    if built is None:
        raise ValueError(f"A panel is over the {max_mb:g}MB cap on its own, even at {PSNR_FLOORS[-1]:g} dB PSNR - "
                         f"raise the cap.")

    written = []
    for index, part in enumerate(built, start=1):
        path = out_dir / f"panels_{index}.pdf"
        path.write_bytes(part.pdf)
        written.append(path)
    total_mb = sum(p.stat().st_size for p in written) / (1024 * 1024)
    console.print(f"[bold green]✓ PDF of {len(pages)} panels - {len(written)} file(s), {total_mb:.1f}MB, each at most "
                  f"{max_mb:g}MB:[/] {_esc(str(out_dir))} [dim]({_quality_note(pages)})[/]")
    return written
