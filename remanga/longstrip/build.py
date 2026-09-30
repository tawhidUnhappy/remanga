"""A long-strip chapter re-cut into pages: chapters/chapter_N/strip/.

The downloaded images stay exactly as MangaDex sent them (their checksums are
what says a download is complete). The panels are marked on the whole strip
at once in the Strip Marker (webui/strip_*.py) and saved as rows of the
chapter read top to bottom - chapter_N/strip_marks.json. Until there are
marks, mangaEasy's webtoon splitter (split.py) proposes them.

strip/ is built from those panels: each run of same-width images is joined
top to bottom and cut into pages only between two panels, packed up to about
a manga page's shape, and crops.json gets one full-width mark per panel. From
there crops.json, the cut panels and their IDs, the PDF and the video work on
strip/ as on any manga's pages.

chapter_N/strip.json records what it was built from - the downloaded images
and the marks - and it is rebuilt when either changes. Marks made on other
images than the ones on disk (a re-download that changed them) are never
applied to the new ones."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
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
STRIP_MARKS_NAME = "strip_marks.json"
# Bumped when the cutting changes. A strip built by an older version is kept
# while the chapter has marks (see the module doc), and rebuilt when it has none.
SLICER_VERSION = 3
# Panels are packed onto a page until it would pass this height / width - about
# a manga page. A panel taller than that is a page of its own.
TARGET_ASPECT = 1.45
# The shortest panel a mark can make, in strip rows - a slip of the mouse, not a panel.
MIN_MARK_PX = 20


def strip_dir(project: str, chapter: str) -> Path:
    return get_chapter_dir(project, chapter) / STRIP_DIR_NAME


def strip_marks_path(project: str, chapter: str) -> Path:
    return get_chapter_dir(project, chapter) / STRIP_MARKS_NAME


def marking_pages_dir(project: str, chapter: str, build: bool = True) -> Path:
    """The pages a chapter's panels are cut from: pages/ for a manga, strip/
    for a long strip - built first unless `build` is False (for callers that
    only list names and must not spend seconds per chapter)."""
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


# --- the whole strip, as the Strip Marker sees it ---------------------------

@dataclass(frozen=True)
class _Run:
    """Consecutive downloaded images of one width, and where they sit in the
    chapter read top to bottom. A cover or a credits page of another width is
    a run of its own."""
    paths: tuple[Path, ...]
    top: int
    width: int
    height: int


def _runs(sources: list[Path]) -> list[_Run]:
    groups: list[list[tuple[Path, int, int]]] = []
    for path in sources:
        with Image.open(path) as img:
            width, height = ImageOps.exif_transpose(img).size
        if groups and groups[-1][0][1] == width:
            groups[-1].append((path, width, height))
        else:
            groups.append([(path, width, height)])
    runs, top = [], 0
    for group in groups:
        height = sum(h for _, _, h in group)
        runs.append(_Run(tuple(p for p, _, _ in group), top, group[0][1], height))
        top += height
    return runs


def image_layout(project: str, chapter: str) -> list[dict]:
    """The downloaded images in reading order with their size and first row
    in the whole strip - what the Strip Marker stacks up."""
    layout, top = [], 0
    for path in source_pages(project, chapter):
        with Image.open(path) as img:
            width, height = ImageOps.exif_transpose(img).size
        layout.append({"name": path.name, "width": width, "height": height, "top": top})
        top += height
    return layout


def auto_panels(project: str, chapter: str) -> list[Range]:
    """mangaEasy's split of the whole chapter, in strip rows."""
    panels: list[Range] = []
    for run in _runs(source_pages(project, chapter)):
        panels += [(run.top + t, run.top + b) for t, b in split_strip(_stitch(run.paths)).panels]
    return panels


def normalize_marks(panels, total_height: int) -> list[Range]:
    """Marks as the browser sent them, made safe: whole rows inside the strip,
    top to bottom, none overlapping (a later one starts where the one before
    ends), none shorter than MIN_MARK_PX."""
    out: list[Range] = []
    for top, bottom in sorted((max(0, round(float(t))), min(total_height, round(float(b)))) for t, b in panels):
        if out:
            top = max(top, out[-1][1])
        if bottom - top >= MIN_MARK_PX:
            out.append((top, bottom))
    return out


def read_strip_marks(project: str, chapter: str) -> list[Range] | None:
    """The saved marks - None when there are none, or when they were made on
    other downloaded images than the ones on disk now."""
    record = read_json_or(strip_marks_path(project, chapter), None)
    if not record or record.get("sources") != _sources_record(source_pages(project, chapter)):
        return None
    return [tuple(p) for p in record.get("panels", [])]


def write_strip_marks(project: str, chapter: str, panels) -> list[Range]:
    """Saves the Strip Marker's marks (cheap - the strip itself is rebuilt by
    ensure_strip). Returns them as saved."""
    sources = source_pages(project, chapter)
    total = sum(item["height"] for item in image_layout(project, chapter))
    marks = normalize_marks(panels, total)
    write_json(strip_marks_path(project, chapter), {"sources": _sources_record(sources),
                                                    "panels": [list(p) for p in marks]})
    return marks


# --- building strip/ -----------------------------------------------------

def _digest(marks: list[Range] | None) -> str | None:
    return None if marks is None else hashlib.sha1(json.dumps(marks).encode()).hexdigest()


def ensure_strip(project: str, chapter: str) -> Path:
    """strip/ for this chapter, rebuilt if it is missing or what it is made
    from - the downloaded images, the marks - changed. Built from marks, it
    writes crops.json too. Returns its folder."""
    out_dir = strip_dir(project, chapter)
    sources = source_pages(project, chapter)
    if not sources:
        raise FileNotFoundError(f"Chapter {chapter} has no downloaded pages - download it first.")
    record_path = out_dir.with_name(STRIP_RECORD_NAME)
    record = read_json_or(record_path, None) or {}
    marks = read_strip_marks(project, chapter)
    same_sources = record.get("sources") == _sources_record(sources)
    has_crops = get_crops_path(project, chapter).exists()
    built = same_sources and all((out_dir / page["file"]).exists() for page in record.get("pages", []))
    if built and record.get("marks") == _digest(marks) and (
            marks is not None or record.get("version") == SLICER_VERSION or has_crops):
        return out_dir
    if marks is None and strip_marks_path(project, chapter).exists():
        console.print(f"[yellow]Chapter {chapter}'s downloaded pages changed since its panels were marked - "
                      f"those marks no longer fit and are set aside; mark the chapter again.[/]")
    _build(chapter, sources, out_dir, record_path, marks)
    if marks is not None:
        _write_crops(project, chapter, out_dir)
    return out_dir


def _open(path: Path) -> Image.Image:
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


def _stitch(paths) -> Image.Image:
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
    across a real gutter - never where two panels touch: that cut may have
    gone through a bubble, and on one page the two halves can still be
    joined; on two they could not."""
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


def _run_marks(marks: list[Range], run: _Run) -> list[Range]:
    """The marks that fall in one run, in its own rows - a mark reaching over
    into the next run (a cover of another width) is cut at the join."""
    out = []
    for top, bottom in marks:
        top, bottom = max(top, run.top) - run.top, min(bottom, run.top + run.height) - run.top
        if bottom - top >= MIN_MARK_PX:
            out.append((top, bottom))
    return out


def _build(chapter: str, sources: list[Path], out_dir: Path, record_path: Path,
           marks: list[Range] | None) -> None:
    work = out_dir.with_name(out_dir.name + ".part")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    pages_out = []
    forced = 0
    doing = "Cutting" if marks is not None else "Finding the panels in"
    with activity.progress(f"{doing} chapter {chapter}'s long strip", total=len(sources), unit="images") as bar:
        for run in _runs(sources):
            strip = _stitch(run.paths)
            if marks is None:
                found = split_strip(strip)
                panels, forced = found.panels, forced + len(found.forced_cuts)
            else:
                panels = _run_marks(marks, run)
            for top, bottom, page_panels in plan_pages(panels, strip.height, strip.width):
                name = f"{page_stem(chapter, len(pages_out) + 1)}.png"
                strip.crop((0, top, strip.width, bottom)).save(work / name, "PNG", compress_level=6)
                pages_out.append({"file": name, "width": strip.width, "height": bottom - top,
                                  "panels": [list(p) for p in page_panels]})
            bar.advance(len(run.paths))
    shutil.rmtree(out_dir, ignore_errors=True)
    work.replace(out_dir)
    # Beside strip/, not in it: everything that reads pages lists the folder.
    write_json(record_path, {
        "version": SLICER_VERSION,
        "sources": _sources_record(sources),
        "marks": _digest(marks),
        "pages": pages_out,
    })
    panels = sum(len(page["panels"]) for page in pages_out)
    console.print(f"[green]✓ Long strip: {len(sources)} downloaded image(s) -> {panels} panel(s) on "
                  f"{len(pages_out)} page(s)[/]"
                  + (f"\n[yellow]  {forced} very tall panel(s) had to be cut where there was no gutter - "
                     f"check those in the Strip Marker.[/]" if forced else ""))


def _write_crops(project: str, chapter: str, pages_dir: Path) -> None:
    """crops.json from the strip's panels: one full-width mark each, written
    the way the Panel Marker writes it, so the cropper reads it as any
    chapter's."""
    from remanga.webui.marker_state import MarkerState

    crops_path = get_crops_path(project, chapter)
    crops_path.unlink(missing_ok=True)   # so the state below starts from the strip, not stale marks
    state = MarkerState(get_chapter_dir(project, chapter), chapter, pages_dir=pages_dir, long_strip=True)
    for filename, boxes in strip_panels(pages_dir).items():
        state.marks[filename] = [{"id": f"strip-{i}", "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1],
                                  "src": "manual"} for i, b in enumerate(boxes)]
    write_json(crops_path, state.build_crops_json())
