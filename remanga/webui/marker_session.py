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
about exactly one chapter, and knows nothing about being in a list."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from remanga.console import console, escape as _esc
from remanga.json_io import has_real_json_content, read_json, write_json
from remanga.paths import get_chapter_dir
from remanga.webui.marker_state import MarkerState


def has_pages(project_name: str, chapter_num: str) -> bool:
    """Whether this chapter has anything to mark - checked by looking, not by
    loading. A chapter's pages/ folder either has files in it or the chapter
    hasn't been downloaded; either way this must not cost an image decode,
    because it runs once per chapter in the project before the first page is
    ever shown."""
    pages_dir = get_chapter_dir(project_name, chapter_num) / "pages"
    return pages_dir.is_dir() and any(p.is_file() for p in pages_dir.iterdir())


class MarkerSession:
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
        self.finished = threading.Event()

        # The detection queue: chapters (and single pages) waiting for MAGI,
        # worked through by ONE background thread. One, deliberately - each
        # pass spawns a worker subprocess that loads the model onto the GPU,
        # so two at once is not twice as fast, it is two processes fighting
        # over the same card.
        self._jobs: list[tuple[str, list[str] | None]] = []
        self._jobs_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._active: str | None = None
        self.auto_all = False
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

    # --- detection ------------------------------------------------------
    #
    # Everything MAGI does in a session goes through one queue and one worker
    # thread. The alternative - each request spawning its own detection - is
    # several model loads racing for one GPU, and a progress report that
    # can't say what it is progressing through.

    def start_detection(self, config) -> None:
        """Queue MAGI's pass for the chapter now under the cursor, if it
        hasn't had one this session.

        Never in a read-only session, and this is the reason that rule lives
        here rather than at each call site: detection WRITES - it fills
        `marks` for every untouched page - so a viewer opened to check what
        was actually saved would quietly fill up with AI guesses that are in
        nobody's crops.json. A session that cannot save must also not
        invent."""
        if self.read_only or not config.magi_enabled:
            return
        if self.auto_all:
            # Already detecting the whole session; queueing this chapter
            # again would only jump it ahead of chapters queued before it.
            self.queue_all(config)
            return
        self.queue_detection(config, [self.chapter_num])

    def queue_detection(self, config, chapters: list[str], pages: list[str] | None = None) -> list[str]:
        """Adds work to the detection queue and makes sure the worker is
        running. Returns the chapters actually queued.

        A chapter whose pass already ran this session is skipped - `pages`
        aside, which is the "just this page" request and is always honoured,
        because asking for one page explicitly is asking for it again."""
        if self.read_only or not config.magi_enabled:
            return []
        queued: list[str] = []
        with self._jobs_lock:
            pending = {chapter for chapter, _ in self._jobs}
            for chapter in chapters:
                if chapter not in self.chapters:
                    continue
                if pages is None:
                    if chapter in pending or self.state_for(chapter).detect_started:
                        continue
                    self.state_for(chapter).detect_started = True
                self._jobs.append((chapter, pages))
                queued.append(chapter)
        if queued:
            self._ensure_worker(config)
        return queued

    def queue_all(self, config) -> list[str]:
        """Every chapter from the one on screen to the end, then the ones
        before it. In that order because "keep marking" is nearly always
        asked while looking at where you stopped - the chapters ahead are
        the ones about to be needed, and the ones behind are usually already
        done."""
        ordered = self.chapters[self.index:] + self.chapters[:self.index]
        return self.queue_detection(config, ordered)

    def set_auto_all(self, enabled: bool, config) -> None:
        """Turns the keep-going switch on or off for this session. On queues
        everything immediately; off clears what hasn't started yet and lets
        the running chapter finish - killing a pass mid-chapter would waste
        the model load it already paid for and leave half a chapter detected
        with no way to tell which half."""
        self.auto_all = bool(enabled)
        if self.auto_all:
            self.queue_all(config)
            return
        with self._jobs_lock:
            for chapter, pages in self._jobs:
                if pages is None:
                    self.state_for(chapter).detect_started = False
            self._jobs.clear()

    def _ensure_worker(self, config) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._drain_jobs, args=(config,), daemon=True)
        self._worker.start()

    def _drain_jobs(self, config) -> None:
        """The worker: one job at a time until the queue is empty.

        A chapter that isn't the one on screen is saved as soon as its pass
        finishes. That is the whole point of leaving this running - the marks
        it produced are on disk whether or not the session ever gets that
        far, so a power cut, a closed tab or an early Finish costs nothing
        that was already computed."""
        from remanga.webui.detection import run_detection

        while not self.finished.is_set():
            with self._jobs_lock:
                if not self._jobs:
                    self._active = None
                    return
                chapter, pages = self._jobs.pop(0)
                self._active = chapter
            try:
                state = self.state_for(chapter)
                run_detection(state, config, only_pages=pages)
                self.mark_dirty(chapter)
                # The chapter on screen is saved when it's left, like any
                # other; anything else is saved here so a background pass
                # nobody watched still lands on disk.
                if chapter != self.chapter_num and self.auto_save:
                    self.save_chapter(chapter)
            except Exception as e:  # a failed chapter must not end the queue
                console.print(f"[bold red]Detection failed for chapter {_esc(chapter)}:[/] {_esc(str(e))}")
        self._active = None

    def set_auto_save(self, enabled: bool) -> None:
        """Turns automatic writing on or off. Turning it ON immediately
        writes whatever is already unsaved - the switch means "keep this on
        disk", and leaving the backlog in memory would make it mean that
        only from now on."""
        self.auto_save = bool(enabled)
        if self.auto_save:
            for chapter in sorted(self.dirty, key=lambda c: self.chapters.index(c)):
                self.save_chapter(chapter)

    def unsaved_chapters(self) -> list[str]:
        """Chapters with marks that aren't on disk, in session order."""
        return [c for c in self.chapters if c in self.dirty]

    def detection_status(self) -> dict[str, Any]:
        """What the assist card reports: the chapter being detected right
        now, how far in it is, and what's still waiting."""
        with self._jobs_lock:
            queued = [chapter for chapter, _ in self._jobs]
        active = self._active
        state = self._states.get(active) if active else None
        return {
            "auto_all": self.auto_all,
            "auto_save": self.auto_save,
            "unsaved": self.unsaved_chapters(),
            "active": active,
            "active_done": state.detect_done if state else 0,
            "active_total": state.detect_total if state else 0,
            "queued": queued,
        }

    def page_names(self, chapter_num: str) -> list[str]:
        """This chapter's page filenames, in order, WITHOUT opening any of
        them. MarkerState reads every image's real size (it has to - marks
        are in image pixels); the outline only needs names and counts, and
        paying an image decode per page for every chapter in a project just
        to draw a sidebar is how a hundred-chapter session would take a
        minute to open."""
        pages_dir = get_chapter_dir(self.project, chapter_num) / "pages"
        if not pages_dir.is_dir():
            return []
        return sorted(p.name for p in pages_dir.iterdir() if p.is_file())

    def _saved_panel_counts(self, chapter_num: str) -> dict[str, int]:
        """Panels per page as its crops.json has them - the only source for a
        chapter this session hasn't opened yet. Empty for a chapter with no
        crops.json, which reads correctly as "nothing marked here"."""
        crops_path = get_chapter_dir(self.project, chapter_num) / "crops.json"
        if not has_real_json_content(crops_path):
            return {}
        try:
            data = read_json(crops_path)
        except Exception:
            return {}
        counts: dict[str, int] = {}
        for page in data.get("pages", []):
            filename = page.get("page_filename")
            if filename:
                counts[str(filename)] = len(page.get("panels") or [])
        return counts

    def outline(self) -> list[dict[str, Any]]:
        """Every chapter, every page, and how many panels each page has -
        the whole session as one tree for the sidebar to draw.

        Live for chapters already open in this session (their in-memory
        marks, including edits not yet saved), and from crops.json for the
        rest. That distinction is why each chapter says whether it's
        `loaded`: a chapter read off disk is showing you the last saved
        state, and a viewer built to double-check things should not blur
        those two together."""
        out: list[dict[str, Any]] = []
        for index, chapter_num in enumerate(self.chapters):
            state = self._states.get(chapter_num)
            if state is not None:
                pages = [
                    {"index": page["index"], "filename": page["filename"],
                     "panels": len(state.marks.get(page["filename"], []))}
                    for page in state.pages
                ]
            else:
                counts = self._saved_panel_counts(chapter_num)
                pages = [
                    {"index": i, "filename": name, "panels": counts.get(name, 0)}
                    for i, name in enumerate(self.page_names(chapter_num), start=1)
                ]
            out.append({
                "chapter": chapter_num,
                "index": index,
                "loaded": state is not None,
                "pages": pages,
                "panels": sum(page["panels"] for page in pages),
                "marked_pages": sum(1 for page in pages if page["panels"]),
            })
        return out

    def describe(self) -> dict[str, Any]:
        """What the browser needs to know about the session itself - which
        chapter of how many, what the others are called, and whether there's
        one after this. The chapter's own pages/marks come from the
        MarkerState alongside this (see routes.py)."""
        return {
            "project": self.project,
            "chapter": self.chapter_num,
            "chapter_index": self.index,
            "chapter_total": len(self.chapters),
            "chapters": list(self.chapters),
            "has_next": self.has_next,
            "read_only": self.read_only,
            "auto_all": self.auto_all,
            "auto_save": self.auto_save,
        }
