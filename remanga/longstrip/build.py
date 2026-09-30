"""A long-strip chapter re-cut into pages: chapters/chapter_N/strip/.

The downloaded images stay exactly as MangaDex sent them (their checksums are
what says a download is complete). strip/ is built from them: each run of
same-width images is joined top to bottom, and cut again only in the blank
bands between panels (gaps.plan_pages), so no panel is ever split across two
pages. Everything after this - the Panel Marker, MAGI, crops.json, the cut
panels and their IDs - works on strip/ as it would on any manga's pages.

chapter_N/strip.json records what it was built from. It is rebuilt when the downloaded
images change, and otherwise never: crops.json is marks in strip/'s pixels,
so a strip cut differently under existing marks would put every one of them
in the wrong place."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from remanga import activity
from remanga.chapters import page_stem
from remanga.console import console
from remanga.json_io import read_json_or, write_json
from remanga.longstrip.gaps import plan_pages, row_spread
from remanga.longstrip.layout import is_long_strip, source_pages
from remanga.paths import get_chapter_dir, get_crops_path, get_pages_dir

STRIP_DIR_NAME = "strip"
STRIP_RECORD_NAME = "strip.json"
# Bumped when the cutting changes. A strip built by an older version is kept
# while the chapter has marks (see the module doc), and rebuilt when it has none.
SLICER_VERSION = 1


def strip_dir(project: str, chapter: str) -> Path:
    return get_chapter_dir(project, chapter) / STRIP_DIR_NAME


def marking_pages_dir(project: str, chapter: str, build: bool = True) -> Path:
    """The pages a chapter's panels are marked and cut on: pages/ for a manga,
    strip/ for a long strip - built first unless `build` is False (for
    callers that only list names and must not spend seconds per chapter)."""
    if not is_long_strip(project, chapter):
        return get_pages_dir(project, chapter)
    if build:
        ensure_strip(project, chapter)
    return strip_dir(project, chapter)


def _sources_record(paths: list[Path]) -> list[list]:
    return [[p.name, p.stat().st_size] for p in paths]


def ensure_strip(project: str, chapter: str) -> Path:
    """strip/ for this chapter, built if it is missing or its downloaded images
    changed. Returns its folder."""
    out_dir = strip_dir(project, chapter)
    sources = source_pages(project, chapter)
    if not sources:
        raise FileNotFoundError(f"Chapter {chapter} has no downloaded pages - download it first.")
    record_path = out_dir.with_name(STRIP_RECORD_NAME)
    record = read_json_or(record_path, None) or {}
    same_sources = record.get("sources") == _sources_record(sources)
    has_marks = get_crops_path(project, chapter).exists()
    built = same_sources and all((out_dir / page["file"]).exists() for page in record.get("pages", []))
    if built and (record.get("version") == SLICER_VERSION or has_marks):
        return out_dir
    if has_marks and record:
        console.print(f"[yellow]Chapter {chapter}'s downloaded pages changed since its panels were marked - "
                      f"the long strip is cut again, so check the marks in the Panel Marker.[/]")
    _build(chapter, sources, out_dir, record_path)
    return out_dir


@dataclass(frozen=True)
class _Run:
    """Consecutive downloaded images of one width, read as one tall image."""
    paths: tuple[Path, ...]
    tops: tuple[int, ...]  # each image's first row in the run
    heights: tuple[int, ...]
    width: int
    height: int


def _runs(sources: list[Path]) -> list[_Run]:
    runs: list[list[tuple[Path, int, int]]] = []
    for path in sources:
        with Image.open(path) as img:
            w, h = ImageOps.exif_transpose(img).size
        if runs and runs[-1][0][1] == w:
            runs[-1].append((path, w, h))
        else:
            runs.append([(path, w, h)])
    out = []
    for run in runs:
        tops, y = [], 0
        for _, _, h in run:
            tops.append(y)
            y += h
        out.append(_Run(tuple(p for p, _, _ in run), tuple(tops), tuple(h for _, _, h in run), run[0][1], y))
    return out


def _open(path: Path) -> Image.Image:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB" if img.mode not in ("L", "RGB") else img.mode)


def _run_spread(run: _Run) -> np.ndarray:
    parts = []
    for path in run.paths:
        with Image.open(path) as img:
            parts.append(row_spread(np.asarray(ImageOps.exif_transpose(img).convert("L"))))
    return np.concatenate(parts)


def _page_image(run: _Run, top: int, bottom: int, cache: dict[Path, Image.Image]) -> tuple[Image.Image, list]:
    """Rows [top, bottom) of the run, pasted from the images they fall in,
    and which rows of which image each piece came from."""
    pieces = []
    for path, first, img_h in zip(run.paths, run.tops, run.heights, strict=True):
        y0, y1 = max(top, first), min(bottom, first + img_h)
        if y0 < y1:
            pieces.append((path, first, y0, y1))
    # Drop images the pages have moved past, so a run holds one or two open.
    for path in list(cache):
        if path not in {p for p, *_ in pieces}:
            del cache[path]
    for path, *_ in pieces:
        if path not in cache:
            cache[path] = _open(path)
    images = [cache[path] for path, *_ in pieces]
    mode = "RGB" if any(img.mode == "RGB" for img in images) else "L"
    page = Image.new(mode, (run.width, bottom - top))
    for (_, first, y0, y1), img in zip(pieces, images, strict=True):
        page.paste(img.crop((0, y0 - first, run.width, y1 - first)).convert(mode), (0, y0 - top))
    return page, [[path.name, y0 - first, y1 - first] for path, first, y0, y1 in pieces]


def _build(chapter: str, sources: list[Path], out_dir: Path, record_path: Path) -> None:
    runs = _runs(sources)
    work = out_dir.with_name(out_dir.name + ".part")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    pages_out = []
    with activity.progress(f"Cutting chapter {chapter}'s long strip into pages", total=len(sources),
                           unit="images") as bar:
        for run in runs:
            cache: dict[Path, Image.Image] = {}
            for top, bottom in plan_pages(_run_spread(run), run.width):
                page, came_from = _page_image(run, top, bottom, cache)
                name = f"{page_stem(chapter, len(pages_out) + 1)}.png"
                page.save(work / name, "PNG", compress_level=6)
                pages_out.append({"file": name, "width": page.width, "height": page.height, "from": came_from})
            bar.advance(len(run.paths))
    shutil.rmtree(out_dir, ignore_errors=True)
    work.replace(out_dir)
    # Beside strip/, not in it: everything that reads pages lists the folder.
    write_json(record_path, {
        "version": SLICER_VERSION,
        "sources": _sources_record(sources),
        "pages": pages_out,
    })
    console.print(f"[green]✓ Long strip: {len(sources)} downloaded image(s) -> {len(pages_out)} page(s), "
                  f"cut only between panels[/]")
