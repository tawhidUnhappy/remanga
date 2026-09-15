"""In-memory state for ONE chapter being marked: the loaded pages, each
page's marks, which pages the user has touched, and MAGI detection progress.
No Flask/HTTP here - see routes.py for the API that reads/writes this,
detection.py for what fills apply_detected() in from a background thread,
and marks_file.py for loading and assembling crops.json.

One chapter, deliberately. A session spanning several of them is a list of
these plus a cursor - see marker_session.py - so nothing in this file has to
know whether it's the only chapter or the fourth of twenty.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PIL import Image

from remanga.webui.mark_ops import order_changed, reading_order
from remanga.webui.marks_file import MarksFileMixin


class MarkerState(MarksFileMixin):
    """All in-memory state for one chapter's marking."""

    def __init__(self, chapter_dir: Path, chapter_num: str):
        # Absolute: Flask's send_from_directory() resolves a relative directory
        # against the app's root_path (remanga/webui/), not the process cwd.
        self.chapter_dir = chapter_dir.resolve()
        self.chapter_num = chapter_num
        self.pages_dir = self.chapter_dir / "pages"
        self.pages: list[dict[str, Any]] = []
        self.marks: dict[str, list[dict[str, Any]]] = {}
        # Pages MAGI must not overwrite: anything with marks on it, plus any
        # page the user deliberately emptied.
        self.touched: set = set()
        # Pages the user deliberately made empty - a decision, and the only
        # thing written to crops.json as such. Strictly smaller than
        # `touched`: see set_marks for why the two can't be the same set.
        self.decided: set = set()
        self.detect_running = False
        self.detect_done = 0
        self.detect_total = 0
        self.detect_error: str | None = None
        # Whether a detection pass has already been run for this chapter this
        # session. A second Detect over it (a range or All chapters that
        # includes it again) would only re-send MAGI the pages it already
        # found nothing on, so it is skipped; the This page scope is how to
        # ask again for one page (see MarkerSession.queue_detection).
        self.detect_started = False
        # Bumped whenever the SERVER rewrites marks the browser is holding (a
        # reorder). The browser compares it on every status poll and reloads
        # the chapter when it moves; without that, its own copy of the old
        # order would be flushed straight back over the new one the next time
        # it autosaved.
        self.revision = 0
        # Held around every change to `marks`. Three threads can reach one
        # chapter at once - a browser autosave, the detection worker, and a
        # reorder - and a reorder that read a page just before a detection
        # replaced it would write the old page back over MAGI's result.
        self.lock = threading.RLock()
        self._load_pages()

    def _load_pages(self) -> None:
        existing_pages = sorted(p for p in self.pages_dir.iterdir() if p.is_file()) if self.pages_dir.exists() else []
        for i, path in enumerate(existing_pages, start=1):
            with Image.open(path) as img:
                w, h = img.size
            self.pages.append({"index": i, "filename": path.name, "width": w, "height": h})
            self.marks.setdefault(path.name, [])
        self._load_existing_crops()

    def set_marks(self, filename: str, marks: list[dict[str, Any]],
                  order_direction: str | None = None) -> list[dict[str, Any]]:
        """Stores a page's marks as the browser sent them, and works out
        whether anything actually happened.

        This is called on every autosave, and the browser autosaves the page
        you are LEAVING - so paging through a chapter to look at it posts an
        unchanged empty list for every page on the way. Treating that as an
        edit is what made simply visiting a page count as "I decided this
        page has no panels": the pages a person scrolled past came back
        excluded, and MAGI never looked at them again.

        So an empty list is only a decision when the page had something on it
        a moment ago. Emptying a page is an act; arriving at one that was
        already empty is not."""
        with self.lock:
            previous = self.marks.get(filename) or []
            if order_direction and len(marks) > 1:
                # Auto-order: stored in reading order however the marks were
                # drawn. Returned so the route can hand the browser the order it
                # actually saved, and the panel numbers on screen stay the real ones.
                marks = reading_order(marks, order_direction)
            self.marks[filename] = marks
            if marks:
                self.touched.add(filename)
                # It isn't an empty page any more, so it isn't a decision about
                # one either - drawing on a page you had cleared takes it back.
                self.decided.discard(filename)
            elif previous:
                # Went from marked to empty: the user cleared it on purpose.
                self.touched.add(filename)
                self.decided.add(filename)
            return marks

    def apply_detected(self, filename: str, boxes: list[list[float]], force: bool = False,
                       order_direction: str | None = None) -> None:
        """Fills in MAGI's detected boxes for a page, unless the user already
        touched that page (never clobber a manual edit with a late-arriving
        background detection).

        `force` is for the one request that names a single page: pressing Run
        with the "This page" scope is asking for this page specifically, so a
        previous "no panels here" - including one inherited from a file too
        old to say who decided it - gives way. It still cannot cost anything:
        a page that HAS marks is refused even when forced, because that is
        the case where there is something to lose."""
        with self.lock:
            if filename in self.touched and (self.marks.get(filename) or not force):
                return
            # A forced pass that fills a page the user had emptied ends that
            # decision: the page has panels now, and leaving the flag set would
            # have it written back to crops.json as "deliberately empty".
            if boxes:
                self.decided.discard(filename)
            self.marks[filename] = self._ai_marks(filename, boxes, order_direction)

    @staticmethod
    def _ai_marks(filename: str, boxes: list[list[float]], order_direction: str | None) -> list[dict[str, Any]]:
        marks = [
            {"id": f"ai-{filename}-{i}", "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1], "src": "ai"}
            for i, b in enumerate(boxes)
        ]
        # The auto-order switch reaching detection: MAGI returns panels in
        # whatever order it found them, and with auto-order on a freshly
        # detected page has to arrive in reading order, or "every chapter
        # stays in order" would only hold for pages somebody had touched.
        if order_direction and len(marks) > 1:
            marks = reading_order(marks, order_direction)
        return marks

    def replace_with_detected(self, detected: dict[str, list[list[float]]],
                              order_direction: str | None = None) -> int:
        """Remark: each page in `detected` gets MAGI's boxes in place of
        whatever it had - hand-drawn marks, edits, a "no panels here" - and
        goes back to being an untouched, undecided page, exactly as if it had
        just been detected for the first time. Returns how many pages changed.

        Everything is applied at once, under the lock, after the whole pass
        has come back: a pass that dies half-way replaces nothing, rather than
        leaving a chapter where some pages are the old marks and some the new
        with no way to tell which. A page MAGI returned nothing for (it failed
        on that page) isn't in `detected`, so it keeps its marks.

        Bumps `revision` so the tab holding this chapter drops its copy and
        reloads - its autosave would otherwise put the old marks straight back."""
        with self.lock:
            replaced = 0
            for filename, boxes in detected.items():
                if filename not in self.marks:
                    continue
                self.marks[filename] = self._ai_marks(filename, boxes, order_direction)
                self.touched.discard(filename)
                self.decided.discard(filename)
                replaced += 1
            if replaced:
                self.revision += 1
            return replaced

    # --- server-side rewrites of the marks -----------------------------

    def _selected(self, filenames: list[str] | None) -> list[str]:
        return list(filenames) if filenames is not None else [p["filename"] for p in self.pages]

    def reorder_pages(self, filenames: list[str] | None, direction: str) -> int:
        """Puts each page's marks into reading order (mark_ops.reading_order).
        Returns how many pages actually changed order.

        A page that changed is flagged touched: its order is now a choice, and
        a detection pass still due for this chapter must not replace it with
        MAGI's."""
        with self.lock:
            changed = 0
            for filename in self._selected(filenames):
                marks = self.marks.get(filename) or []
                ordered = reading_order(marks, direction)
                if order_changed(marks, ordered):
                    self.marks[filename] = ordered
                    self.touched.add(filename)
                    changed += 1
            if changed:
                self.revision += 1
            return changed
