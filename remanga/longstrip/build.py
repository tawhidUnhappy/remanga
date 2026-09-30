"""A long-strip chapter re-cut into pages: chapters/chapter_N/strip/.

The downloaded images stay exactly as MangaDex sent them (their checksums are
what says a download is complete). strip/ is built from them: each run of
same-width images is joined top to bottom, its panels are found by
mangaEasy's webtoon splitter (split.py), and the run is cut into pages only
between two panels, packed up to about a manga page's shape. Each page's
panels are recorded, and they are what Detect puts on that page - no MAGI.
From there the Panel Marker, crops.json, the cut panels and their IDs work on
strip/ as on any manga's pages.

chapter_N/strip.json records what it was built from. It is rebuilt when the
downloaded images change, and otherwise never: crops.json is marks in
strip/'s pixels, so a strip cut differently under existing marks would put
every one of them in the wrong place."""

from __future__ import annotations

import shutil
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageOps

from remanga import activity
from remanga.chapters import page_stem
from remanga.console import console
from remanga.json_io import read_json_or, write_json
from remanga.longstrip.layout import is_long_strip, source_pages
from remanga.longstrip.split import Range, split_strip
from remanga.paths import get_chapter_dir, get_crops_path, get_pages_dir

STRIP_DIR_NAME = "strip"
STRIP_RECORD_NAME = "strip.json"
# Bumped when the cutting changes. A strip built by an older version is kept
# while the chapter has marks (see the module doc), and rebuilt when it has none.
SLICER_VERSION = 2
# Panels are packed onto a page until it would pass this height / width - about
# a manga page. A panel taller than that is a page of its own.
TARGET_ASPECT = 1.45


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


def strip_panels(pages_dir: Path) -> dict[str, list[list[float]]]:
    """Each strip page's panels as marks-to-be: full-width [x1, y1, x2, y2]
    boxes in the page's pixels. Empty for a folder that is not a strip."""
    record = read_json_or(pages_dir.with_name(STRIP_RECORD_NAME), None) or {}
    return {page["file"]: [[0.0, float(top), float(page["width"]), float(bottom)]
                           for top, bottom in page.get("panels", [])]
            for page in record.get("pages", [])}


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
    if has_marks and record and not same_sources:
        console.print(f"[yellow]Chapter {chapter}'s downloaded pages changed since its panels were marked - "
                      f"the long strip is cut again, so check the marks in the Panel Marker.[/]")
    _build(chapter, sources, out_dir, record_path)
    return out_dir


def _open(path: Path) -> Image.Image:
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


def _runs(sources: list[Path]) -> list[list[Path]]:
    """Consecutive downloaded images of one width: one strip each. A cover or
    a credits page of another width stays a run of its own."""
    runs: list[list[Path]] = []
    last_width = None
    for path in sources:
        with Image.open(path) as img:
            width = ImageOps.exif_transpose(img).width
        if runs and width == last_width:
            runs[-1].append(path)
        else:
            runs.append([path])
        last_width = width
    return runs


def _stitch(paths: list[Path]) -> Image.Image:
    images = [_open(p) for p in paths]
    strip = Image.new("RGB", (images[0].width, sum(im.height for im in images)))
    y = 0
    for im in images:
        strip.paste(im, (0, y))
        y += im.height
    return strip


def plan_pages(panels: list[Range], height: int, width: int) -> list[tuple[int, int, list[Range]]]:
    """The strip as pages that tile it top to bottom, each (top, bottom, its
    panels in page rows). Whole panels only, and a page is cut only halfway
    across a real gutter - never on an auto-split cut, where two panels
    touch: that cut may have gone through a bubble (a forced cut), and on one
    page the two halves can still be joined in the marker; on two they could
    not."""
    if not panels:
        return [(0, height, [])]
    groups: list[list[Range]] = [[panels[0]]]
    for panel in panels[1:]:
        touching = panel[0] <= groups[-1][-1][1]
        if not touching and panel[1] - groups[-1][0][0] > width * TARGET_ASPECT:
            groups.append([panel])
        else:
            groups[-1].append(panel)
    cuts = [0] + [(prev[-1][1] + nxt[0][0]) // 2 for prev, nxt in pairwise(groups)] + [height]
    return [(top, bottom, [(t - top, b - top) for t, b in group])
            for (top, bottom), group in zip(pairwise(cuts), groups, strict=True)]


def _build(chapter: str, sources: list[Path], out_dir: Path, record_path: Path) -> None:
    work = out_dir.with_name(out_dir.name + ".part")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    pages_out = []
    forced = 0
    with activity.progress(f"Finding the panels in chapter {chapter}'s long strip", total=len(sources),
                           unit="images") as bar:
        for run in _runs(sources):
            strip = _stitch(run)
            found = split_strip(strip)
            forced += len(found.forced_cuts)
            for top, bottom, panels in plan_pages(found.panels, strip.height, strip.width):
                name = f"{page_stem(chapter, len(pages_out) + 1)}.png"
                strip.crop((0, top, strip.width, bottom)).save(work / name, "PNG", compress_level=6)
                pages_out.append({"file": name, "width": strip.width, "height": bottom - top,
                                  "panels": [list(p) for p in panels]})
            bar.advance(len(run))
    shutil.rmtree(out_dir, ignore_errors=True)
    work.replace(out_dir)
    # Beside strip/, not in it: everything that reads pages lists the folder.
    write_json(record_path, {
        "version": SLICER_VERSION,
        "sources": _sources_record(sources),
        "pages": pages_out,
    })
    panels = sum(len(page["panels"]) for page in pages_out)
    console.print(f"[green]✓ Long strip: {len(sources)} downloaded image(s) -> {panels} panel(s) on "
                  f"{len(pages_out)} page(s)[/]"
                  + (f"\n[yellow]  {forced} very tall panel(s) had to be cut where there was no gutter - "
                     f"check those in the Panel Marker (s splits a mark, drag an edge to join).[/]" if forced else ""))
