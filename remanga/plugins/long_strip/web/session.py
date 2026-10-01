"""One Strip Marker session: a long-strip chapter's images, the detection
that proposes and snaps its marks, and the marks themselves - no HTTP here
(server.py is the routes).

Detection runs once, when the tab first asks for the chapter (~2-4 s), and is
kept: the verified gutters are what an edge snaps to while marking, and the
borders found with no gutter (and panels left tall) are what the tab uses to
fit a new panel on a double click and flags for a look."""

from __future__ import annotations

import threading

from remanga.paths import load_project_metadata
from remanga.plugins.long_strip.build import proposed_marks
from remanga.plugins.long_strip.gutters import group_of
from remanga.plugins.long_strip.layout import source_pages
from remanga.plugins.long_strip.marks import Mark, read_marks, write_marks
from remanga.plugins.long_strip.runs import runs_of
from remanga.plugins.long_strip.tiles import StripView


class StripSession:
    def __init__(self, project: str, chapter: str):
        self.project, self.chapter = project, chapter
        self.sources = source_pages(project, chapter)
        if not self.sources:
            raise FileNotFoundError(f"Chapter {chapter} has no downloaded pages - download it first.")
        self.view = StripView(runs_of(self.sources))
        self.total_height = sum(run.height for run in self.view.runs)
        self.finished = threading.Event()
        self._lock = threading.Lock()
        self._proposed: list[Mark] | None = None
        self._found: dict | None = None

    def _detect(self) -> None:
        """Detection once per session, in whole-chapter rows."""
        with self._lock:
            if self._found is not None:
                return
            self._proposed, detections = proposed_marks(self.view)
            gutters, borders, tall = [], [], []
            for run, found in zip(self.view.runs, detections, strict=True):
                gutters += [{"top": run.top + g.top, "bottom": run.top + g.bottom, "color": list(g.color),
                             "strength": g.strength} for g in found.gutters]
                borders += [run.top + y for y in found.borders]
                tall += [[run.top + a, run.top + b] for a, b in found.tall]
            self._found = {"gutters": gutters, "borders": borders, "tall": tall}

    def proposed(self) -> list[Mark]:
        self._detect()
        return list(self._proposed or [])

    def marks(self) -> tuple[list[Mark], bool]:
        """The saved marks, or (the first time) the proposed ones, saved now -
        and whether they were proposed."""
        saved = read_marks(self.project, self.chapter, self.sources)
        if saved is not None:
            return saved, False
        return self.save(self.proposed()), True

    def save(self, raw) -> list[Mark]:
        return write_marks(self.project, self.chapter, self.sources, raw, self.total_height)

    def layout(self) -> dict:
        """What the tab needs to put the strip on screen at once - image
        headers only, no detection (that is payload, a few seconds later)."""
        return {
            "project": self.project,
            "title": load_project_metadata(self.project).get("manga_title", self.project),
            "chapter": self.chapter,
            "runs": self.view.layout(),
            "total_height": self.total_height,
        }

    def payload(self) -> dict:
        marks, proposed = self.marks()
        self._detect()
        # One swatch per colour as the detector groups them (near-whites are one white).
        groups: list[tuple[int, int, int]] = []
        colors: dict[int, dict] = {}
        for gutter in self._found["gutters"]:
            key = group_of(tuple(gutter["color"]), groups)
            entry = colors.setdefault(key, {"color": gutter["color"], "strength": "local", "count": 0})
            entry["count"] += 1
            if gutter["strength"] == "strong":
                entry["strength"] = "strong"
        return {
            "project": self.project,
            "title": load_project_metadata(self.project).get("manga_title", self.project),
            "chapter": self.chapter,
            "runs": self.view.layout(),
            "total_height": self.total_height,
            "panels": [list(m) for m in marks],
            "proposed": proposed,
            "gutters": self._found["gutters"],
            "borders": self._found["borders"],
            "tall": self._found["tall"],
            "colors": sorted(colors.values(), key=lambda c: -c["count"]),
        }
