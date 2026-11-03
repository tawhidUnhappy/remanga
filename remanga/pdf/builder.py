"""A chapter's panels as PDF files for the LLM, never over the size cap.

Two steps, each in its own module: every panel is encoded losslessly
(encode.py), then the panels are packed into as many parts as the cap needs
(pack.py). Each part starts with a text page - the chapter's identity,
reading direction, which panels this part holds, the chapter's full panel
list, and the story so far (manifest_info.py).

The crop PDF (workflow/crop_pdf.py) is built the same way from its drawn pages,
with its own text page, each page at its own size (build_image_pdf).

Why not Pillow's own PDF writer: it re-encodes every image as JPEG, with no
way to turn that off (see writer.py)."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from remanga.console import console, escape as _esc
from remanga.pdf.encode import PSNR_FLOORS, lossless_page
from remanga.pdf.manifest_info import build_part_info, info_to_text_lines
from remanga.pdf.pack import _Built, _pack_parts, _Page, _quality_note
from remanga.pdf.writer import build_pdf

_WORKERS = min(8, os.cpu_count() or 1)

# A part's text page: (every image's name, this part's, part number, part count) -> its lines.
PartText = Callable[[list[str], list[str], int, int], list[str]]


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
    def text(full_ids: list[str], part_ids: list[str], index: int, total: int) -> list[str]:
        return info_to_text_lines(build_part_info(info, full_ids, part_ids, index, total))

    # panels_*.pdf, and any pages_*.pdf from before. Each page is its panel's
    # own size: an LLM prices every PDF page the same (Gemini 3: 560 tokens),
    # and on a page the size of the chapter's biggest panel the typical panel
    # filled a sixth of it - the rest of what each page cost went on black.
    return build_image_pdf(image_paths, out_dir, max_mb, "panels", text, own_size=True, stale="p*_*.pdf")


def build_image_pdf(image_paths: Sequence[Path], out_dir: Path, max_mb: float, name: str, text: PartText, *,
                    own_size: bool = False, stale: str | None = None, noun: str = "panels") -> list[Path]:
    """`out_dir`/<name>_1.pdf, <name>_2.pdf, ... from `image_paths`, in order,
    each at most `max_mb` and each starting with its `text` page. `own_size`:
    every image page is its image's size (writer.build_pdf); otherwise all of
    them are the biggest image's, the image centred on black. The old parts
    (`stale`, a glob - default <name>_*.pdf) go first."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(stale or f"{name}_*.pdf"):
        old.unlink()
    max_bytes = max(1, int(max_mb * 1024 * 1024))

    paths = list(image_paths)
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        lossless = list(pool.map(lossless_page, paths))
    pages = [_Page(path.stem, path, page) for path, page in zip(paths, lossless, strict=True)]
    full_ids = [page.stem for page in pages]
    # Without `own_size`, every image page of every part is the size of the
    # biggest image, the image centred on black, so the parts of a split PDF
    # match each other.
    canvas = (max(page.page.width for page in pages), max(page.page.height for page in pages))

    def render(part: Sequence[_Page], index: int, total: int) -> _Built:
        lines = text(full_ids, [page.stem for page in part], index, total)
        return _Built(build_pdf([page.page for page in part], lines, canvas, own_size=own_size))

    built = _pack_parts(pages, max_bytes, render)
    if built is None:
        raise ValueError(f"A {noun[:-1]} is over the {max_mb:g}MB cap on its own, even at {PSNR_FLOORS[-1]:g} dB "
                         f"PSNR - raise the cap.")

    written = []
    for index, part in enumerate(built, start=1):
        path = out_dir / f"{name}_{index}.pdf"
        path.write_bytes(part.pdf)
        written.append(path)
    total_mb = sum(p.stat().st_size for p in written) / (1024 * 1024)
    console.print(f"[bold green]✓ PDF of {len(pages)} {noun} - {len(written)} file(s), {total_mb:.1f}MB, each at most "
                  f"{max_mb:g}MB:[/] {_esc(str(out_dir))} [dim]({_quality_note(pages, noun)})[/]")
    return written
