"""A chapter as PDF files for the LLM, never over the size cap: every page
with its panel marks drawn on it, and every panel cut out of those pages.

Three steps, each in its own module: the pages are drawn (marked_pages.py),
every image is encoded losslessly (encode.py), then they are packed into as
many parts as the cap needs (pack.py). Each part starts with a text page -
the chapter's identity, reading direction, which pages and panels this part
holds, the chapter's full panel list, and the story so far
(manifest_info.py).

The order inside a part is the order it is read in: a page, then the panels
cut from that page, then the next page (user request, 2026-09-22). The panels
alone were never enough to see a layout - which panels share a tier, what an
inset sits inside, where a character is looking across a spread - and that is
what a page is for. The panels still are what gets narrated; the pages are
what they are read in.

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
from remanga.pdf.manifest_info import PAGE_PANELS_KEY, PAGES_KEY, build_part_info, info_to_text_lines
from remanga.pdf.marked_pages import MarkedPage
from remanga.pdf.pack import _Built, _pack_parts, _Page, _quality_note
from remanga.pdf.writer import build_pdf

_WORKERS = min(8, os.cpu_count() or 1)


def _reading_order(pages: Sequence[MarkedPage], panels: Sequence[Path]) -> list[tuple[Path, str, str]]:
    """The images in the order they go into the PDF - each page followed by
    the panels cut from it - as (path, name, kind).

    Driven by the panels actually on disk, matched to pages by name: a panel
    the pages don't claim (a crops.json and a panels/ that have drifted apart)
    still goes in, after the pages, rather than being silently dropped from
    the upload. Every panel reaches the LLM or none of this is worth
    anything."""
    by_stem = {path.stem: path for path in panels}
    order: list[tuple[Path, str, str]] = []
    claimed: set[str] = set()
    for page in pages:
        order.append((page.path, page.stem, "page"))
        for stem in page.panel_stems:
            path = by_stem.get(stem)
            if path is not None:
                order.append((path, stem, "panel"))
                claimed.add(stem)
    order.extend((path, path.stem, "panel") for path in panels if path.stem not in claimed)
    return order


def build_chapter_pdf(
    pages: Sequence[MarkedPage],
    panels: Sequence[Path],
    out_dir: Path,
    max_mb: float,
    info: dict[str, Any],
) -> list[Path]:
    """Writes `out_dir`/panels_1.pdf, panels_2.pdf, ... from the chapter's
    marked pages and cut panels, each at most `max_mb`, replacing any parts
    from an earlier build. `info` is the chapter's identity and anything else
    the text page should carry. Returns the parts written; raises when an
    image can't be encoded or can't fit under the cap."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("p*_*.pdf"):  # panels_*.pdf, and any pages_*.pdf from before
        stale.unlink()
    max_bytes = max(1, int(max_mb * 1024 * 1024))

    ordered = _reading_order(pages, panels)
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        lossless = list(pool.map(lossless_page, [path for path, _stem, _kind in ordered]))
    items = [_Page(stem, path, page, kind=kind)
             for (path, stem, kind), page in zip(ordered, lossless, strict=True)]
    panels_per_page = {page.stem: list(page.panel_stems) for page in pages}
    # The manifest is the panels, and only the panels: they are the entries
    # the reply must have one of each, and a page is not one of them.
    full_ids = [item.stem for item in items if item.kind == "panel"]
    # Every page of every part is the size of the biggest image, with the
    # image centred on black: pages and panels are all different shapes, and a
    # PDF that changes shape on every scroll is hard to read.
    canvas = (max(item.page.width for item in items), max(item.page.height for item in items))

    def render(part: Sequence[_Page], index: int, total: int) -> _Built:
        part_pages = [item.stem for item in part if item.kind == "page"]
        part_info = build_part_info(
            info, full_ids, [item.stem for item in part if item.kind == "panel"], index, total,
            extra={PAGES_KEY: part_pages,
                   PAGE_PANELS_KEY: {stem: panels_per_page.get(stem, []) for stem in part_pages}},
        )
        return _Built(build_pdf([item.page for item in part], info_to_text_lines(part_info), canvas))

    built = _pack_parts(items, max_bytes, render)
    if built is None:
        raise ValueError(f"An image is over the {max_mb:g}MB cap on its own, even at {PSNR_FLOORS[-1]:g} dB PSNR - "
                         f"raise the cap.")

    written = []
    for index, part in enumerate(built, start=1):
        path = out_dir / f"panels_{index}.pdf"
        path.write_bytes(part.pdf)
        written.append(path)
    total_mb = sum(p.stat().st_size for p in written) / (1024 * 1024)
    console.print(f"[bold green]✓ PDF of {len(pages)} marked pages and {len(full_ids)} panels - "
                  f"{len(written)} file(s), {total_mb:.1f}MB, each at most {max_mb:g}MB:[/] "
                  f"{_esc(str(out_dir))} [dim]({_quality_note(items)})[/]")
    return written
