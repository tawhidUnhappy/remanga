"""Building a chapter's LLM crop upload - the grid formats of LLMCropConfig
(a folder, a zip, a PDF, each single or split) - plus the empty
llm_crops.json Gemini's reply is pasted into.

Laid out the way `package` lays out a cropped chapter. The gridded pages are
generated into grid_pages/chapter_N/ with a 000_info image, the way sheets/
carries one, and the zip and PDF formats are built from those files by the
very builders panels_zip and panels_pdf use (zip_bundle.build_zip_bundle,
llm_pdf.build_pdf_bundle): lossless re-encoding, optional size-capped parts,
and chapter_info.json - or the PDF's leading text page - with the chapter's
identity, `contents` and `full_manifest`. On top of that, every format says
what this workflow needs Gemini to know: the grouping setting, the grid's
spec, and each page's area inside its square (see grid.PageExtent)."""

from __future__ import annotations

import contextlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from remanga.console import console, escape as _esc
from remanga.cropper.llm_pdf import build_pdf_bundle
from remanga.cropper.sheets import PanelSheetGenerator
from remanga.cropper.zip_bundle import build_zip_bundle
from remanga.extensions.llm_crop.config import LLMCropConfig
from remanga.extensions.llm_crop.grid import oriented_size, page_extent, render_grid_page
from remanga.extensions.llm_crop.paths import (
    get_grid_pages_dir,
    get_grid_pdf_dir,
    get_grid_zip_dir,
    get_llm_crops_path,
)
from remanga.paths import chapter_identity_fields, get_chapter_dir, load_project_metadata

INFO_STEM = "000_info"


@dataclass(frozen=True)
class ChapterPage:
    """One downloaded page. `index` is its 1-based position in pages/ - the
    page_index the Panel Marker writes, and what panel filenames number
    against."""

    stem: str
    path: Path
    index: int


@dataclass(frozen=True)
class GridBuild:
    images: list[Path]
    zips: list[Path]
    pdfs: list[Path]
    reply: Path


def chapter_pages(project_name: str, chapter_num: str) -> list[ChapterPage]:
    """Every file in the chapter's pages/, in order - listed exactly the way
    the marker lists them, so page_index means the same thing either way."""
    pages_dir = get_chapter_dir(project_name, chapter_num) / "pages"
    files = sorted(p for p in pages_dir.iterdir() if p.is_file()) if pages_dir.exists() else []
    return [ChapterPage(path.stem, path, i) for i, path in enumerate(files, start=1)]


def grid_info(llm: LLMCropConfig, pages: list[ChapterPage]) -> dict[str, Any]:
    """What every grid format adds to the chapter's info, for Gemini to read
    (prompts/llm_crop.md <inputs>)."""
    return {
        "grouping": llm.grouping,
        "grid": {
            "image_size": llm.grid_image_size,
            "line_step": llm.grid_line_step,
            "label_step": llm.grid_label_step,
            "tick_step": llm.grid_tick_step,
        },
        "page_areas": {page.stem: page_extent(*oriented_size(page.path)).box for page in pages},
    }


def ensure_reply_file(project_name: str, chapter_num: str) -> Path:
    """llm_crops.json, created empty - zero bytes, the placeholder state the
    rest of remanga reads as "not written yet" - unless something is already
    there, which is never touched."""
    path = get_llm_crops_path(project_name, chapter_num)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return path


def _render_one(page: ChapterPage, out_dir: Path, llm: LLMCropConfig) -> Path:
    """One grid image, saved as a plain lossless PNG. Not shrunk here: the
    zip builder already picks the smallest lossless encoding of every image
    it packs, and doing it twice doubled the time of a chapter's build for
    nothing (measured: 118s for 40 pages, the zip saving 0.0MB over it)."""
    with Image.open(page.path) as img:
        grid = render_grid_page(img, page.stem, llm.grid_image_size, llm.grid_line_step,
                                llm.grid_label_step, llm.grid_tick_step)
    path = out_dir / f"{page.stem}.png"
    grid.save(path, "PNG", compress_level=6)
    return path


def generate_grid_pages(llm: LLMCropConfig, project_name: str, chapter_num: str,
                        pages: list[ChapterPage], extra: dict[str, Any]) -> list[Path]:
    """Draws every page into grid_pages/chapter_N/ and returns the page
    images (not the 000_info image, which the zip and PDF formats replace
    with chapter_info.json and a text page)."""
    out_dir = get_grid_pages_dir(project_name, chapter_num)
    # A full wipe first, same rule as sheets/: a page removed upstream, or a
    # different size setting, must not leave a stale image behind.
    for old in out_dir.iterdir():
        if old.is_file():
            with contextlib.suppress(Exception):
                old.unlink()

    console.print(
        f"[cyan]Drawing {len(pages)} gridded page(s) ({llm.grid_image_size}px squares, "
        f"lines every {llm.grid_line_step}, labeled every {llm.grid_label_step}"
        + (f", ticks every {llm.grid_tick_step}" if llm.grid_tick_step else "") + ")...[/]"
    )
    # Threads, not processes: Pillow releases the GIL while resizing and
    # encoding, which is where the time goes.
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        images = list(pool.map(lambda page: _render_one(page, out_dir, llm), pages))

    info = dict(chapter_identity_fields(project_name, chapter_num))
    info.update(extra)
    info["total_items"] = len(pages)
    info["contents"] = [page.stem for page in pages]
    info["full_manifest"] = info["contents"]
    PanelSheetGenerator.render_info_sheet(info, out_dir)
    console.print(f"[bold green]✓ Drew {len(images)} gridded pages in:[/] {_esc(str(out_dir))}")
    return images


def build_grid_bundles(llm: LLMCropConfig, project_name: str, chapter_num: str) -> GridBuild:
    """Builds every active grid format for one chapter, and its reply file."""
    pages = chapter_pages(project_name, chapter_num)
    if not pages:
        raise FileNotFoundError(
            f"No downloaded pages for chapter {chapter_num}: "
            f"{get_chapter_dir(project_name, chapter_num) / 'pages'}\nRun `download` first."
        )
    if not llm.any_active:
        raise ValueError("Every grid format is switched off - turn one on in Settings → LLM crop.")
    # Gemini numbers each page's crops in reading order, so the direction is
    # required here the way `package` requires it - never guessed.
    if "reading_direction" not in load_project_metadata(project_name):
        raise ValueError(
            f"Missing 'reading_direction' for project '{project_name}' - Gemini needs it to order "
            f"the crops. Run `remanga interactive` once for this project (it asks and saves it), or "
            f"add \"reading_direction\": \"right_to_left\" (or \"left_to_right\") to "
            f"projects/{project_name}/project.json."
        )

    extra = grid_info(llm, pages)
    images = generate_grid_pages(llm, project_name, chapter_num, pages, extra)
    zips = build_zip_bundle(
        images, get_grid_zip_dir(project_name, chapter_num, create=False), "grid",
        llm.grid_zip, llm.grid_zip_splites, llm.max_mb, project_name, chapter_num, "GRID ZIP",
        extra_info=extra,
    )
    pdfs = build_pdf_bundle(
        images, get_grid_pdf_dir(project_name, chapter_num, create=False), "grid",
        llm.grid_pdf, llm.grid_pdf_splite, llm.grid_pdf_zip, llm.grid_pdf_zip_splite, llm.max_mb,
        project_name, chapter_num, "GRID PDF", extra_info=extra,
    )
    return GridBuild(images=images, zips=zips, pdfs=pdfs, reply=ensure_reply_file(project_name, chapter_num))


def grid_built(llm: LLMCropConfig, project_name: str, chapter_num: str) -> bool:
    """Whether every active grid format has something on disk - the same
    "is it up to date" question llm_bundles.is_up_to_date asks for panels."""
    pages_dir = get_grid_pages_dir(project_name, chapter_num, create=False)
    pdf_dir = get_grid_pdf_dir(project_name, chapter_num, create=False)
    pages_ok = not llm.grid_pages or any(p.stem != INFO_STEM for p in pages_dir.glob("*.*"))
    zip_ok = not llm.zip_active or any(get_grid_zip_dir(project_name, chapter_num, create=False).glob("grid_*.zip"))
    pdf_ok = not llm.pdf_active or any(pdf_dir.glob("grid_*.pdf")) or any(pdf_dir.glob("grid_*.zip"))
    return llm.any_active and pages_ok and zip_ok and pdf_ok
