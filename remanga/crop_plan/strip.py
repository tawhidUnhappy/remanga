"""A crop plan's edits applied to a long strip's panels (a webtoon chapter: one
tall strip, cut across between panels). A panel is (top, bottom) in rows of
the whole chapter (plugins/long_strip/runs.py); a cut is the row half way
between two panels in a row, which is the number labelled on the crop PDF's
red lines and on Claude's sheets.

    split ROW         a new cut at ROW
    join ROW          the cut nearest ROW goes: the two panels become one
    move ROW NEWROW   the cut nearest ROW moves to NEWROW
    drop ROW          the panel holding ROW goes (credits, ads)
    add TOP BOTTOM    a panel of its own (overlaps allowed)

Edits apply one after another, each to what the one before left."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

from remanga.crop_plan.grammar import StripEdit

Span = tuple[int, int]

NEAREST = 400       # how far a join or move looks for the cut it names
MIN_ROWS = 20       # plugins/long_strip/marks.py MIN_MARK_ROWS: a panel shorter is no panel


@dataclass
class StripNow:
    """A chapter's strip as it is: its images, the view that draws and detects
    it, and its panels - the saved marks, else the detector's proposal."""
    sources: list[Path]
    view: object
    panels: list[Span]
    saved: bool
    proposed: list[Span]

    @property
    def height(self) -> int:
        return self.view.runs[-1].bottom


def strip_now(project: str, chapter: str) -> StripNow:
    from remanga.plugins.long_strip.build import proposed_marks
    from remanga.plugins.long_strip.layout import source_pages
    from remanga.plugins.long_strip.marks import read_marks
    from remanga.plugins.long_strip.runs import runs_of
    from remanga.plugins.long_strip.tiles import StripView

    sources = source_pages(project, chapter)
    if not sources:
        raise FileNotFoundError(f"Chapter {chapter} has no downloaded pages - download it first.")
    view = StripView(runs_of(sources))
    saved = read_marks(project, chapter, sources)
    proposed = sorted((m[0], m[1]) for m in proposed_marks(view)[0])
    panels = sorted((m[0], m[1]) for m in saved) if saved else proposed
    return StripNow(sources, view, panels, saved is not None, proposed)


def cuts_of(panels: list[Span]) -> list[int]:
    panels = sorted(panels)
    return [round((a[1] + b[0]) / 2) for a, b in itertools.pairwise(panels)]


@dataclass
class StripOutcome:
    panels: list[Span]
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def apply_edits(panels: list[Span], edits: list[StripEdit], height: int) -> StripOutcome:
    """`panels` with every edit applied in turn. An edit that names no cut or
    panel is an error, and the rest still run, so every problem is listed."""
    out = StripOutcome(sorted(panels))
    marks = out.panels

    def cut_near(row: int) -> int | None:
        if len(marks) < 2:
            return None
        best = min(range(len(marks) - 1), key=lambda i: abs((marks[i][1] + marks[i + 1][0]) / 2 - row))
        return best if abs((marks[best][1] + marks[best + 1][0]) / 2 - row) <= NEAREST else None

    def holding(row: int) -> int | None:
        return next((i for i, (top, bottom) in enumerate(marks) if top <= row < bottom), None)

    for edit in edits:
        where = f"line {edit.line} (`{edit.text}`)"
        rows = edit.rows
        if any(not 0 <= r <= height for r in rows):
            out.errors.append(f"{where}: the strip has rows 0-{height}")
            continue
        if edit.op in ("join", "move"):
            i = cut_near(rows[0])
            if i is None:
                out.errors.append(f"{where}: no cut within {NEAREST} rows of {rows[0]} - use the row on a red label")
                continue
            if edit.op == "join":
                marks[i:i + 2] = [(marks[i][0], max(marks[i][1], marks[i + 1][1]))]
            elif not marks[i][0] + MIN_ROWS <= rows[1] <= marks[i + 1][1] - MIN_ROWS:
                out.errors.append(f"{where}: {rows[1]} is not between the two panels the cut parts "
                                  f"({marks[i][0]}-{marks[i + 1][1]})")
                continue
            else:
                marks[i], marks[i + 1] = (marks[i][0], rows[1]), (rows[1], marks[i + 1][1])
        elif edit.op in ("split", "drop"):
            i = holding(rows[0])
            if i is None:
                out.errors.append(f"{where}: no panel holds row {rows[0]}")
                continue
            top, bottom = marks[i]
            if edit.op == "drop":
                del marks[i]
            elif not top + MIN_ROWS <= rows[0] <= bottom - MIN_ROWS:
                out.errors.append(f"{where}: {rows[0]} is too near the panel's own edge ({top}-{bottom})")
                continue
            else:
                marks[i:i + 1] = [(top, rows[0]), (rows[0], bottom)]
        elif rows[1] - rows[0] < MIN_ROWS:
            out.errors.append(f"{where}: TOP must be over BOTTOM by at least {MIN_ROWS} rows")
            continue
        else:
            marks.append((rows[0], rows[1]))
        marks.sort()
        out.changed.append(f"{edit.text}  ->  {len(marks)} panels")
    return out
