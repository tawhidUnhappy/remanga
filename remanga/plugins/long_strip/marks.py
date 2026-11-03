"""A long strip's panel marks: what the Strip Marker saves, in
chapter_N/strip_marks.json.

A mark is [top, bottom, left, right]: top and bottom are rows of the whole
chapter (runs.py), left and right are shares of the width (0..1) - always the
full width: a strip is cut across only, never down (user request, 2026-10-16),
and sides saved before that are read as full width. Marks may
overlap (a bubble that belongs to two panels): only nonsense is cleaned up,
never an overlap. The file carries the downloaded images' fingerprint, and
marks made on other images are never applied to the ones on disk."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remanga.json_io import read_json_or, write_json
from remanga.paths import get_chapter_dir

Mark = tuple[int, int, float, float]

MARKS_NAME = "strip_marks.json"
MIN_MARK_ROWS = 20


def marks_path(project: str, chapter: str) -> Path:
    return get_chapter_dir(project, chapter) / MARKS_NAME


def sources_record(paths: list[Path]) -> list[list]:
    """The downloaded images as marks were made on them: name and size."""
    return [[p.name, p.stat().st_size] for p in paths]


def normalize(raw, total_height: int) -> list[Mark]:
    """Marks as the browser sent them, made safe: whole rows inside the strip,
    full width (any sides sent are dropped), nothing too short to be a panel,
    exact duplicates dropped; sorted top to bottom. Overlaps are kept."""
    out: set[Mark] = set()
    for item in raw or []:
        top, bottom = float(item[0]), float(item[1])
        top, bottom = max(0, round(min(top, bottom))), min(total_height, round(max(top, bottom)))
        if bottom - top >= MIN_MARK_ROWS:
            out.add((top, bottom, 0.0, 1.0))
    return sorted(out)


def read_marks(project: str, chapter: str, sources: list[Path]) -> list[Mark] | None:
    """The saved marks - None when there are none, or when they were made on
    other downloaded images than `sources`."""
    record = read_json_or(marks_path(project, chapter), None)
    if not record or record.get("sources") != sources_record(sources):
        return None
    return normalize(record.get("panels", []), 1 << 31)


def write_marks(project: str, chapter: str, sources: list[Path], raw, total_height: int) -> list[Mark]:
    marks = normalize(raw, total_height)
    write_json(marks_path(project, chapter), {"sources": sources_record(sources),
                                              "panels": [list(m) for m in marks]})
    return marks


def digest(marks: list[Mark] | None) -> str | None:
    """What strip.json records the strip was built from, so a change is seen."""
    return None if marks is None else hashlib.sha1(json.dumps(marks).encode()).hexdigest()
