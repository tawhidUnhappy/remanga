"""Marks from panels already cut: each panel image is found in the chapter's
long strip by its pixels, and the rows it sits at become the strip's marks
(what the Strip Marker would have saved).

For a manga whose panels were cut before - an older remanga, or another
tool - so they need not be marked by hand again. A panel that is not found
whole (resized, edited, from other pages) is reported and left unmarked; a
chapter with any such panel is not saved, so a half-marked chapter never
passes for a marked one."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from remanga.console import console, escape as _esc
from remanga.paths import get_project_dir
from remanga.plugins.long_strip.layout import source_pages
from remanga.plugins.long_strip.marks import write_marks
from remanga.plugins.long_strip.runs import runs_of, stitch


def panels_folder(project: str, chapter: str) -> Path:
    """Where cut panels are looked for: import_zip/<NN>/panels in the project."""
    return get_project_dir(project) / "import_zip" / f"{int(float(chapter)):02d}" / "panels"


def _rows(image: np.ndarray) -> list[int]:
    return [hash(row.tobytes()) for row in image]


# A panel saved from the same pages but encoded again differs from them by
# noise of a fraction of a level; one cut from other pages by tens.
FUZZY_MAX_DIFF = 2.0
SIGNATURE_ROWS = 200


def _gray(image: np.ndarray) -> np.ndarray:
    return image.astype(np.float32).mean(axis=2)


def _fuzzy_top(strip_gray: np.ndarray, strip_signature: np.ndarray, panel: np.ndarray) -> int | None:
    """Where `panel` sits in the strip when its pixels differ a little: the
    row signature of its first rows is slid down the strip, and the best place
    is kept only if the whole panel agrees there."""
    from numpy.lib.stride_tricks import sliding_window_view

    gray = _gray(panel)
    rows = min(SIGNATURE_ROWS, len(gray))
    if len(strip_gray) < len(gray):
        return None
    head = gray[:rows, ::10].mean(axis=1)
    cost = np.abs(sliding_window_view(strip_signature, rows) - head).mean(axis=1)[:len(strip_gray) - len(gray) + 1]
    top = int(cost.argmin())
    return top if float(np.abs(strip_gray[top:top + len(gray)] - gray).mean()) <= FUZZY_MAX_DIFF else None


def find_marks(strip: np.ndarray, panels: list[Path]) -> tuple[list[tuple[int, int]], list[str]]:
    """(top, bottom) rows of every panel found in `strip`, and the names of
    those that were not. Panels come in reading order, so each is looked for
    from the end of the one before first, then anywhere."""
    strip_rows = _rows(strip)
    strip_gray = strip_signature = None
    where: dict[int, list[int]] = {}
    for y, key in enumerate(strip_rows):
        where.setdefault(key, []).append(y)
    found: list[tuple[int, int]] = []
    missing: list[str] = []
    after = 0
    for path in panels:
        with Image.open(path) as img:
            panel = np.asarray(img.convert("RGB"))
        top = None
        if panel.shape[1] == strip.shape[1] and len(panel):
            keys = _rows(panel)
            starts = sorted(where.get(keys[0], []), key=lambda y: (y < after, y))
            top = next((y for y in starts if strip_rows[y:y + len(keys)] == keys), None)
        if top is None and panel.shape[1] == strip.shape[1] and len(panel):
            if strip_gray is None:
                strip_gray = _gray(strip)
                strip_signature = strip_gray[:, ::10].mean(axis=1)
            top = _fuzzy_top(strip_gray, strip_signature, panel)
        if top is None:
            missing.append(path.name)
        else:
            found.append((top, top + len(panel)))
            after = top + len(panel)
    return found, missing


def marks_from_panels(project: str, chapter: str, panels: list[Path] | None = None) -> bool:
    """Saves the strip marks of a long-strip chapter from its cut panels
    (`panels`, else panels_folder). True when every panel was found and the
    marks were saved."""
    panels = panels if panels is not None else sorted(panels_folder(project, chapter).glob("*.png"))
    sources = source_pages(project, chapter)
    if not panels or not sources:
        console.print(f"[yellow]Chapter {chapter}: no {'panels' if not panels else 'downloaded pages'} - skipped.[/]")
        return False
    runs = runs_of(sources)
    if len(runs) != 1:
        console.print(f"[yellow]Chapter {chapter}: its pages are not all one width - mark it by hand.[/]")
        return False
    found, missing = find_marks(np.asarray(stitch(runs[0])), panels)
    if missing:
        console.print(f"[yellow]Chapter {chapter}: {len(missing)} of {len(panels)} panels not found in the "
                      f"pages ({_esc(', '.join(missing[:5]))}{'…' if len(missing) > 5 else ''}) - "
                      f"nothing saved; mark it by hand.[/]")
        return False
    write_marks(project, chapter, sources, [[top, bottom] for top, bottom in found], runs[0].height)
    console.print(f"[green]✓ Chapter {chapter}: {len(found)} panels marked from the old panels[/]")
    return True
