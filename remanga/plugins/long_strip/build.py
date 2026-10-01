"""A long-strip chapter's strip/ pages and crops.json, kept in step with what
they are made from.

The downloaded images stay exactly as MangaDex sent them (their checksums say
a download is complete). The panels are marked on the whole strip in the
Strip Marker (marks.py); until there are marks, detect.py proposes them.
strip/ is built from the panels - each run joined top to bottom and cut into
pages between them (pages.py) - and, when they are marks, crops.json too
(crops.py). From there the cut panels, the PDF and the video work on strip/
as on any manga's pages.

chapter_N/strip.json (beside strip/, never in it - everything that reads
pages lists that folder) records what the strip was built from: the images
and the marks. Either changing rebuilds it."""

from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from remanga import activity
from remanga.chapters import page_stem
from remanga.console import console
from remanga.json_io import read_json_or, write_json
from remanga.paths import get_chapter_dir, get_crops_path
from remanga.plugins.long_strip.crops import page_boxes, write_crops
from remanga.plugins.long_strip.layout import source_pages
from remanga.plugins.long_strip.marks import Mark, digest, marks_path, read_marks, sources_record
from remanga.plugins.long_strip.pages import plan_pages, run_marks
from remanga.plugins.long_strip.runs import Run, runs_of
from remanga.plugins.long_strip.tiles import StripView

STRIP_DIR_NAME = "strip"
STRIP_RECORD_NAME = "strip.json"
# Bumped when the cutting changes: an unmarked strip is then proposed again.
SLICER_VERSION = 4


def strip_dir(project: str, chapter: str) -> Path:
    return get_chapter_dir(project, chapter) / STRIP_DIR_NAME


def strip_panels(pages_dir: Path) -> dict[str, list[list[float]]]:
    """Each strip page's panels as [x1, y1, x2, y2] boxes in its pixels."""
    record = read_json_or(pages_dir.with_name(STRIP_RECORD_NAME), None) or {}
    return {page["file"]: [[float(v) for v in box] for box in page_boxes(page)] for page in record.get("pages", [])}


def proposed_marks(view: StripView) -> tuple[list[Mark], list]:
    """detect.py's panels for every run, as full-width marks in chapter rows,
    and the detections themselves (gutters, borders and tall panels, in run rows)."""
    detections = view.detect()
    marks = [(run.top + top, run.top + bottom, 0.0, 1.0)
             for run, found in zip(view.runs, detections, strict=True) for top, bottom in found.panels]
    return marks, detections


def ensure_strip(project: str, chapter: str) -> Path:
    """strip/ for this chapter, rebuilt when it is missing or its images or
    marks changed; with marks, crops.json is rewritten from them. Returns
    the folder."""
    out_dir = strip_dir(project, chapter)
    sources = source_pages(project, chapter)
    if not sources:
        raise FileNotFoundError(f"Chapter {chapter} has no downloaded pages - download it first.")
    record_path = out_dir.with_name(STRIP_RECORD_NAME)
    record = read_json_or(record_path, None) or {}
    marks = read_marks(project, chapter, sources)
    built = (record.get("sources") == sources_record(sources)
             and all((out_dir / page["file"]).exists() for page in record.get("pages", [])))
    current = record.get("marks") == digest(marks) and (marks is not None or record.get("version") == SLICER_VERSION)
    if built and current:
        return out_dir
    if marks is None and marks_path(project, chapter).exists():
        console.print(f"[yellow]Chapter {chapter}'s downloaded pages changed since its panels were marked - "
                      f"those marks no longer fit and are set aside; mark the chapter again.[/]")
    runs = runs_of(sources)
    view = StripView(runs)
    if marks is None:
        with activity.progress(f"Finding the panels in chapter {chapter}'s long strip"):
            proposed, _ = proposed_marks(view)
    pages = _build(chapter, view, marks if marks is not None else proposed, out_dir)
    write_json(record_path, {"version": SLICER_VERSION, "sources": sources_record(sources),
                             "marks": digest(marks), "pages": pages})
    if marks is not None:
        write_crops(get_crops_path(project, chapter), chapter, pages)
    total = sum(len(page["panels"]) for page in pages)
    console.print(f"[green]✓ Long strip: {len(sources)} downloaded image(s) -> {total} panel(s) on "
                  f"{len(pages)} page(s)[/]")
    return out_dir


def _build(chapter: str, view: StripView, marks: list[Mark], out_dir: Path) -> list[dict]:
    """Writes strip/ (atomically: a .part folder renamed into place) and
    returns its pages as strip.json records them."""
    work = out_dir.with_name(out_dir.name + ".part")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    pages: list[dict] = []
    with activity.progress(f"Cutting chapter {chapter}'s long strip into pages", total=len(view.runs),
                           unit="runs") as bar:
        for index, run in enumerate(view.runs):
            pages += _write_run(chapter, view.image(index), run, marks, work, len(pages))
            bar.advance()
    shutil.rmtree(out_dir, ignore_errors=True)
    work.replace(out_dir)
    return pages


# strip/ is a private step between the download and the cut panels (which are
# compressed properly), so its pages are written fast: level 1 is still
# lossless, and with the pages saved in parallel Finish went from ~15 s to ~2 s
# on a 98,000-row chapter (12.5 s of it was level-6 compression, one at a time).
STRIP_PNG_LEVEL = 1


def _write_run(chapter: str, image, run: Run, marks: list[Mark], work: Path, done: int) -> list[dict]:
    planned = plan_pages(run_marks(marks, run.top, run.height), run.height, run.width)
    pages = [{"file": f"{page_stem(chapter, done + i + 1)}.png", "width": run.width, "height": bottom - top,
              "panels": [list(m) for m in page_marks]} for i, (top, bottom, page_marks) in enumerate(planned)]

    def save(i: int) -> None:
        top, bottom, _ = planned[i]
        image.crop((0, top, run.width, bottom)).save(work / pages[i]["file"], "PNG", compress_level=STRIP_PNG_LEVEL)

    with ThreadPoolExecutor(max_workers=min(len(planned), os.cpu_count() or 1)) as pool:
        list(pool.map(save, range(len(planned))))
    return pages

