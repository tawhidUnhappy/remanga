"""One marking session, over one chapter or every chapter in a project.

The marker used to be strictly one chapter per run: open the browser, mark,
save, the tab closes, the server dies, and marking the next chapter starts
the whole ceremony again - a new port, a new tab, a new MAGI load, and a
person clicking through a browser launch twenty times to do one afternoon's
work.

This is the piece that makes it a session instead. It owns the ordered list
of chapters and one MarkerState per chapter, built lazily - a hundred-chapter
project must not open three thousand page images to show you the first one -
and it is what "next chapter" means server-side: write this chapter's
crops.json, move the cursor, hand the browser the next chapter's pages. The
tab never reloads and the process never restarts, so the marks you just made
are still one click away when you want to check them.

MarkerState (marker_state.py) is untouched by any of this: it still knows
about exactly one chapter, and knows nothing about being in a list.

The session's other jobs each live in a module of their own, mixed into
MarkerSession: the MAGI detection queue (session_detection.py), remarking,
reordering and the save switches (session_edits.py), and the sidebar outline
(session_outline.py)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from remanga.console import console, escape as _esc
from remanga.json_io import write_json
from remanga.paths import get_chapter_dir, load_project_metadata
from remanga.webui.marker_state import MarkerState
from remanga.webui.session_detection import DetectionQueueMixin
from remanga.webui.session_edits import MarkEditsMixin
from remanga.webui.session_outline import SessionOutlineMixin


def has_pages(project_name: str, chapter_num: str) -> bool:
    """Whether this chapter has anything to mark - checked by looking, not by
    loading. A chapter's pages/ folder either has files in it or the chapter
    hasn't been downloaded; either way this must not cost an image decode,
    because it runs once per chapter in the project before the first page is
    ever shown."""
    pages_dir = get_chapter_dir(project_name, chapter_num) / "pages"
    return pages_dir.is_dir() and any(p.is_file() for p in pages_dir.iterdir())


class MarkerSession(DetectionQueueMixin, MarkEditsMixin, SessionOutlineMixin):
    """The chapters one browser tab will work through, and where it is.

    `finished` is the whole process's stop signal: the Flask server runs
    until it's set (see server.py), which happens when the last chapter is
    saved, or when the user ends the session early. It lives here rather
    than on a MarkerState because a chapter finishing is no longer the same
    event as the session finishing."""

    def __init__(self, project_name: str, chapters: list[str], read_only: bool = False):
        self.project = project_name
        # A session that can look but not touch (`view-marks`). Enforced on
        # the server, not just hidden in the browser: a read-only session
        # must not be one stray fetch away from rewriting a chapter's marks,
        # and the point of opening one is to trust what it shows.
        self.read_only = read_only
        self.chapters = [c for c in chapters if has_pages(project_name, c)]
        self.skipped = [c for c in chapters if c not in set(self.chapters)]
        if not self.chapters:
            first = chapters[0] if chapters else "?"
            raise FileNotFoundError(
                f"No downloaded pages found in {get_chapter_dir(project_name, first) / 'pages'} - "
                f"download the chapter first."
            )
        self.index = 0
        self._states: dict[str, MarkerState] = {}
        self._states_lock = threading.Lock()
        self.saved: list[Path] = []
        # The same, as chapter numbers in the order first written - what Save
        # reports back to the tab.
        self.saved_chapters: list[str] = []
        self.finished = threading.Event()

        # The detection queue: chapters (and single pages) waiting for MAGI,
        # worked through by ONE background thread. One, deliberately - each
        # pass spawns a worker subprocess that loads the model onto the GPU,
        # so two at once is not twice as fast, it is two processes fighting
        # over the same card.
        # Each job is {"kind": "detect" | "remark", "chapter", "pages" (None =
        # every page), "force", "replace"}. Only MAGI work is queued - it's the
        # part that needs the GPU. Reorder runs straight away in the request
        # (see reorder()).
        self._jobs: list[dict[str, Any]] = []
        self._jobs_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        # True from the moment a worker is started until it has decided, under
        # the lock, that the queue is empty. Checking thread.is_alive() instead
        # left a window where a job queued just as the worker was exiting saw a
        # thread still alive, started nothing, and sat in the queue unrun.
        self._worker_busy = False
        self._active: str | None = None
        self._active_kind: str | None = None
        # Progress across everything queued since the queue was last idle, so
        # the card can report the RUN ("3 of 7") instead of whichever chapter
        # happens to be mid-pass - see detection_status.
        self._run_total = 0
        self._run_done = 0
        self._run_kinds: set[str] = set()
        self._run_chapters: set[str] = set()
        self._last_run: dict[str, Any] | None = None
        # Keep marks in reading order as they are saved (config.auto_order).
        self.auto_order = False
        # Whether a chapter is written to disk on its own - when you leave
        # it, and when the detection worker finishes one. Off means only an
        # explicit Save writes anything, so `dirty` is what would be lost:
        # it is what the browser is asked about before the session closes,
        # rather than letting the switch quietly cost someone their work.
        self.auto_save = True
        self.dirty: set[str] = set()

    @property
    def chapter_num(self) -> str:
        return self.chapters[self.index]

    def state_for(self, chapter_num: str) -> MarkerState:
        """One chapter's state, built the first time it's asked for and kept
        afterwards - so going back to chapter 3 to check a mark shows the
        marks you made this session, not a re-read of what's on disk.

        By NAME, not "the current one", because the detection worker runs
        against a chapter while the user is free to navigate somewhere else:
        a background pass that followed the cursor would write chapter 6's
        detections into whatever chapter happened to be on screen when they
        landed. The lock is for the same reason - two threads asking for an
        unbuilt chapter at once must not each build one and disagree about
        which is real."""
        with self._states_lock:
            state = self._states.get(chapter_num)
            if state is None:
                state = MarkerState(get_chapter_dir(self.project, chapter_num), chapter_num)
                self._states[chapter_num] = state
            return state

    @property
    def current(self) -> MarkerState:
        return self.state_for(self.chapter_num)

    @property
    def has_next(self) -> bool:
        return self.index + 1 < len(self.chapters)

    @property
    def reading_direction(self) -> str:
        """How this manga is read - what "reading order" means for it."""
        return load_project_metadata(self.project).get("reading_direction") or "right_to_left"

    def save_current(self) -> Path | None:
        """Writes the current chapter's crops.json and says so. Called on
        every chapter change, not only at the end: leaving a chapter is the
        moment its marks stop being visible, so it's the moment they have to
        be on disk rather than only in this process's memory."""
        return self.save_chapter(self.chapter_num)

    def mark_dirty(self, chapter_num: str) -> None:
        """This chapter has marks that aren't on disk yet."""
        self.dirty.add(chapter_num)

    def save_chapter(self, chapter_num: str) -> Path | None:
        """Writes one chapter's crops.json. By name, because the detection
        worker finishes chapters nobody has opened yet: without this their
        marks would live only in this process, and a session that ended
        before the user ever navigated there would throw away every minute
        of GPU time that produced them."""
        if self.read_only:
            return None
        state = self.state_for(chapter_num)
        with state.lock:
            crops = state.build_crops_json()
        crops_path = state.chapter_dir / "crops.json"
        write_json(crops_path, crops)
        total_panels = sum(len(page["panels"]) for page in crops["pages"])
        console.print(
            f"[bold green]✓ Chapter {_esc(chapter_num)}: saved {total_panels} marked panel(s) "
            f"across {len(crops['pages'])} page(s) to:[/] {_esc(str(crops_path))}"
        )
        if crops_path not in self.saved:
            self.saved.append(crops_path)
        if chapter_num not in self.saved_chapters:
            self.saved_chapters.append(chapter_num)
        self.dirty.discard(chapter_num)
        return crops_path

    def goto(self, index: int, *, save: bool = True) -> bool:
        """Moves to another chapter in the list, saving the one being left.
        False for an index that isn't a chapter in this session.

        `save=False` is for the one caller that has already written the
        current chapter itself (/api/finish, which saves and then advances) -
        without it that chapter's crops.json would be written twice in a
        row, and the terminal would report the same save twice.

        With auto-save off, leaving a chapter writes nothing; the marks stay
        in this session (they are still there when you come back) and the
        chapter is remembered as unsaved."""
        if not 0 <= index < len(self.chapters):
            return False
        if index != self.index:
            if save and self.auto_save:
                self.save_current()
            self.index = index
        return True
