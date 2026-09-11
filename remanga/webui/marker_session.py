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
from remanga.paths import get_chapter_dir, load_project_metadata
from remanga.webui.marker_state import DECIDED_KEY, MarkerState


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
        # Each job is {"kind": "detect", "chapter", "pages" (None = every
        # page), "force"}. Only detection is queued - it's the part that needs
        # the GPU. Reorder runs straight away in the request (see reorder()).
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
        self.auto_all = False
        # Keep marks in reading order as they are saved (config.auto_order).
        self.auto_order = False
        # The recrop queue: chapters waiting to have their panel images cut
        # again from their marks. Its own worker, separate from detection -
        # cropping is CPU and disk, MAGI is GPU, and neither should wait for
        # the other: a Recrop queued behind an hours-deep Keep-marking run
        # would look exactly like a Recrop that did nothing.
        self._crop_jobs: list[str] = []
        self._crop_lock = threading.Lock()
        self._crop_busy = False
        self._crop_active: str | None = None
        self._crop_run_total = 0
        self._crop_run_done = 0
        self._crop_result: dict[str, Any] = self._empty_crop_result()
        self._crop_last_run: dict[str, Any] | None = None
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

    @property
    def reading_direction(self) -> str:
        """How this manga is read - what "reading order" means for it."""
        return load_project_metadata(self.project).get("reading_direction") or "right_to_left"

    def _begin_run_if_idle(self) -> None:
        """Starts a fresh run count when nothing is queued or running. Caller
        holds _jobs_lock."""
        if self._active is None and not self._jobs:
            self._run_total = self._run_done = 0
            self._run_kinds = set()
            self._run_chapters = set()

    def _note_queued(self, kind: str, chapter: str) -> None:
        self._run_total += 1
        self._run_kinds.add(kind)
        self._run_chapters.add(chapter)

    def queue_detection(self, config, chapters: list[str], pages: list[str] | None = None,
                        force: bool = False) -> list[str]:
        """Adds work to the detection queue and makes sure the worker is
        running. Returns the chapters actually queued.

        A chapter whose pass already ran this session is skipped - `pages`
        aside, which is the "just this page" request and is always honoured,
        because asking for one page explicitly is asking for it again.
        `force` travels with that request down to apply_detected, where it
        lets a page recorded as having no panels be detected after all."""
        if self.read_only or not config.magi_enabled:
            return []
        queued: list[str] = []
        with self._jobs_lock:
            self._begin_run_if_idle()
            pending = {job["chapter"] for job in self._jobs if job["kind"] == "detect"}
            for chapter in chapters:
                if chapter not in self.chapters:
                    continue
                if pages is None:
                    if chapter in pending or self.state_for(chapter).detect_started:
                        continue
                    self.state_for(chapter).detect_started = True
                self._jobs.append({"kind": "detect", "chapter": chapter, "pages": pages, "force": force})
                self._note_queued("detect", chapter)
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
            for job in self._jobs:
                if job["pages"] is None:
                    self.state_for(job["chapter"]).detect_started = False
            self._run_total -= len(self._jobs)
            self._jobs.clear()

    def _ensure_worker(self, config) -> None:
        with self._jobs_lock:
            if self._worker_busy:
                return
            self._worker_busy = True
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
                    self._active_kind = None
                    self._last_run = {
                        "jobs": self._run_done,
                        "kinds": sorted(self._run_kinds),
                        "chapters": [c for c in self.chapters if c in self._run_chapters],
                    }
                    self._worker_busy = False
                    return
                job = self._jobs.pop(0)
                self._active = job["chapter"]
                self._active_kind = job["kind"]
            chapter = job["chapter"]
            try:
                state = self.state_for(chapter)
                # Counters belong to this job; stale numbers from an earlier
                # pass on the same chapter are how "3/3 pages" showed up
                # against a job that had not detected anything yet.
                state.detect_done = state.detect_total = 0
                run_detection(
                    state, config, only_pages=job["pages"], force=job["force"],
                    order_direction=self.reading_direction if self.auto_order else None,
                )
                self.mark_dirty(chapter)
                # The chapter on screen is saved when it's left, like any
                # other; anything else is saved here so a background pass
                # nobody watched still lands on disk.
                if chapter != self.chapter_num and self.auto_save:
                    self.save_chapter(chapter)
            except Exception as e:  # a failed chapter must not end the queue
                console.print(f"[bold red]Detection failed for chapter {_esc(chapter)}:[/] {_esc(str(e))}")
            finally:
                with self._jobs_lock:
                    self._run_done += 1
        with self._jobs_lock:
            self._active = None
            self._active_kind = None
            self._worker_busy = False

    # --- recropping ------------------------------------------------------

    @staticmethod
    def _empty_crop_result() -> dict[str, Any]:
        return {"chapters": [], "panels": 0, "mismatched": [], "failed": [], "skipped": []}

    def chapter_has_marks(self, chapter_num: str) -> bool:
        """Whether a chapter has anything to crop from: its marks in this
        session if it has been opened, otherwise what its crops.json holds."""
        state = self._states.get(chapter_num)
        if state is not None:
            with state.lock:
                return any(state.marks.get(page["filename"]) for page in state.pages)
        return any(panels for panels, _ in self._saved_page_facts(chapter_num).values())

    def chapter_is_narrated(self, chapter_num: str) -> bool:
        return has_real_json_content(get_chapter_dir(self.project, chapter_num) / "narration.json")

    def recrop_plan(self, chapters: list[str]) -> dict[str, list[str]]:
        """What a Recrop over `chapters` would do, without doing any of it: the
        chapters with marks to crop (in session order), the ones with none, and
        which croppable ones already have narration - because a crop that
        changes a chapter's panels changes the panel ids its narration was
        written against, and the browser asks before that."""
        wanted = set(chapters)
        targets = [c for c in self.chapters if c in wanted]
        croppable = [c for c in targets if self.chapter_has_marks(c)]
        return {
            "chapters": croppable,
            "unmarked": [c for c in targets if c not in croppable],
            "narrated": [c for c in croppable if self.chapter_is_narrated(c)],
        }

    def queue_recrop(self, chapters: list[str]) -> list[str]:
        """Queues chapters to have their panels cut again, and starts the crop
        worker if it isn't running. Returns the chapters accepted - one already
        waiting or being cropped isn't queued twice."""
        if self.read_only:
            return []
        accepted: list[str] = []
        start = False
        with self._crop_lock:
            if not self._crop_busy:
                self._crop_run_total = self._crop_run_done = 0
                self._crop_result = self._empty_crop_result()
            for chapter in chapters:
                if chapter not in self.chapters or chapter in self._crop_jobs or chapter == self._crop_active:
                    continue
                self._crop_jobs.append(chapter)
                self._crop_run_total += 1
                accepted.append(chapter)
            # Decided under the lock, like the detection worker: a thread that
            # is already on its way out must not count as "running".
            if accepted and not self._crop_busy:
                self._crop_busy = start = True
        if start:
            threading.Thread(target=self._drain_crops, daemon=True).start()
        return accepted

    def _drain_crops(self) -> None:
        """The recrop worker: one chapter at a time until the queue is empty.

        Each chapter is exactly `remanga crop --force` - panels/ cleared and
        every panel cut again from crops.json - preceded by writing crops.json
        if this session holds marks for it that aren't on disk yet, because the
        cropper reads the file, not the session. That write happens with
        auto-save off too: pressing Recrop is asking for panels cut from the
        marks on screen. A chapter with nothing unsaved is cropped from its
        file as it stands, and never rewritten just to be read back.

        Afterwards each chapter is checked against its narration.json. A crop
        that added, removed or renumbered panels leaves narration naming panels
        that no longer exist, and TTS and render refuse that (verify/gate.py) -
        the time to hear it is now, where the change was made, not when a
        render stops an hour later."""
        from remanga.config import RemangaConfig
        from remanga.cropper import CoordinateCropper
        from remanga.settings.project_prefs import cropper_config_for
        from remanga.verify.panels import check_panel_narration_mismatch

        while not self.finished.is_set():
            with self._crop_lock:
                if not self._crop_jobs:
                    self._crop_active = None
                    self._crop_last_run = self._copy_crop_result()
                    self._crop_busy = False
                    return
                chapter = self._crop_jobs.pop(0)
                self._crop_active = chapter
            outcome: tuple[str, Any] = ("failed", {"chapter": chapter, "error": "interrupted"})
            try:
                if not self.chapter_has_marks(chapter):
                    outcome = ("skipped", chapter)
                else:
                    if chapter in self.dirty:
                        self.save_chapter(chapter)
                    # Loaded per chapter, not once: a cropper setting changed in
                    # the terminal between two chapters of a long run should
                    # apply to the chapters still to come.
                    config = RemangaConfig.load().for_project(self.project)
                    panels = CoordinateCropper(cropper_config_for(config, self.project)).crop_chapter_from_json(
                        self.project, chapter, force=True,
                    )
                    outcome = ("done", (chapter, len(panels), check_panel_narration_mismatch(self.project, chapter)))
            except Exception as e:  # a failed chapter must not end the queue
                console.print(f"[bold red]Recrop failed for chapter {_esc(chapter)}:[/] {_esc(str(e))}")
                outcome = ("failed", {"chapter": chapter, "error": (str(e).splitlines() or [type(e).__name__])[0]})
            finally:
                with self._crop_lock:
                    self._record_crop(outcome)
                    self._crop_run_done += 1
        with self._crop_lock:
            self._crop_active = None
            self._crop_busy = False

    def _record_crop(self, outcome: tuple[str, Any]) -> None:
        """Adds one chapter's outcome to the run. Caller holds _crop_lock."""
        kind, value = outcome
        result = self._crop_result
        if kind == "done":
            chapter, count, issue = value
            result["chapters"].append(chapter)
            result["panels"] += count
            if issue:
                result["mismatched"].append({"chapter": chapter, "issue": issue})
        elif kind == "skipped":
            result["skipped"].append(value)
        else:
            result["failed"].append(value)

    def _copy_crop_result(self) -> dict[str, Any]:
        """A copy safe to hand to jsonify while the worker keeps appending.
        Caller holds _crop_lock."""
        return {key: (list(value) if isinstance(value, list) else value) for key, value in self._crop_result.items()}

    def crop_status(self) -> dict[str, Any]:
        with self._crop_lock:
            return {
                "crop_active": self._crop_active,
                "crop_queued": list(self._crop_jobs),
                "crop_run_done": self._crop_run_done,
                "crop_run_total": self._crop_run_total,
                # The run so far while it's going, and the finished run once it
                # isn't. The finished one stays until the next Recrop: "narration
                # no longer matches" is the one thing here nobody should miss,
                # and a message that fades after a few seconds gets missed.
                "crop_result": self._copy_crop_result(),
                "crop_last_run": self._crop_last_run,
            }

    # --- reading order --------------------------------------------------

    def reorder(self, chapters: list[str], pages: list[str] | None = None) -> dict[str, int]:
        """Puts marks into reading order over `chapters` (only `pages` of them,
        if given), right now, in the calling thread. Returns {chapter: pages
        whose order changed}.

        Not queued behind detection. Reorder needs no GPU and takes
        milliseconds, but with Keep marking on the detection queue can be hours
        deep, and a Reorder that waited its turn behind that is a Reorder that
        looks like it did nothing. Each chapter's lock keeps it from
        interleaving with a detection pass on the same pages.

        A chapter that isn't on screen is saved as soon as it changes (with
        auto-save on), the same rule the detection worker follows."""
        if self.read_only:
            return {}
        direction = self.reading_direction
        result: dict[str, int] = {}
        for chapter in chapters:
            if chapter not in self.chapters:
                continue
            changed = self.state_for(chapter).reorder_pages(pages, direction)
            if not changed:
                continue
            result[chapter] = changed
            self.mark_dirty(chapter)
            if chapter != self.chapter_num and self.auto_save:
                self.save_chapter(chapter)
        return result

    def set_auto_order(self, enabled: bool) -> None:
        """Turns auto-order on or off for this session.

        On means every chapter stays in reading order, not just the pages
        edited from now on - so turning it on reorders the chapter on screen
        immediately (the browser reloads it from the response) and every other
        chapter in the session on a background thread. From then on pages are
        re-sorted on every save and detected pages arrive sorted.

        Off changes nothing that exists; it stops the automatic sorting, which
        is what lets a person set an order the algorithm would get wrong."""
        self.auto_order = bool(enabled)
        if not self.auto_order or self.read_only:
            return
        self.reorder([self.chapter_num])
        others = [c for c in self.chapters if c != self.chapter_num]
        if others:
            threading.Thread(target=self.reorder, args=(others,), daemon=True).start()

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
            queued = [job["chapter"] for job in self._jobs]
            run_total, run_done, last_run = self._run_total, self._run_done, self._last_run
            active, active_kind = self._active, self._active_kind
        state = self._states.get(active) if active else None
        return {
            "auto_all": self.auto_all,
            "auto_save": self.auto_save,
            "auto_order": self.auto_order,
            "unsaved": self.unsaved_chapters(),
            "active": active,
            "active_kind": active_kind,
            "active_done": state.detect_done if state else 0,
            "active_total": state.detect_total if state else 0,
            "queued": queued,
            # The run as a whole: jobs finished / jobs queued since the queue
            # was last idle. The card's bar is this, not the active chapter's
            # own pages - a per-chapter bar resets on every chapter, which in
            # a range run reads as a bar that can't make up its mind.
            "run_done": run_done,
            "run_total": run_total,
            # What the last finished run did, for the idle message. Without it
            # the card had nothing to say once the queue emptied, and kept
            # whatever it said last - "Detecting ch 4 · 2/3 pages", forever.
            "last_run": last_run,
            **self.crop_status(),
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

    def _saved_page_facts(self, chapter_num: str) -> dict[str, tuple[int, bool]]:
        """Per page of a chapter this session hasn't opened: how many panels
        its crops.json records, and whether a person decided that. Empty for
        a chapter with no crops.json, which reads correctly as "nothing here
        and nobody has said otherwise"."""
        crops_path = get_chapter_dir(self.project, chapter_num) / "crops.json"
        if not has_real_json_content(crops_path):
            return {}
        try:
            data = read_json(crops_path)
        except Exception:
            return {}
        entries = data.get("pages", [])
        # Same legacy rule as MarkerState._load_existing_crops: a file that
        # never says who decided anything is read the old way, where every
        # entry counted as a decision.
        records_decisions = any(DECIDED_KEY in entry for entry in entries)
        facts: dict[str, tuple[int, bool]] = {}
        for page in entries:
            filename = page.get("page_filename")
            if not filename:
                continue
            panels = len(page.get("panels") or [])
            decided = bool(page.get(DECIDED_KEY)) if records_decisions else True
            facts[str(filename)] = (panels, decided)
        return facts

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
                     "panels": len(state.marks.get(page["filename"], [])),
                     # An empty page somebody excluded on purpose is a
                     # finished page; an empty page nobody has reached is
                     # work left. The sidebar draws them differently because
                     # telling them apart is most of what checking a
                     # half-done chapter consists of.
                     "decided": page["filename"] in state.decided}
                    for page in state.pages
                ]
            else:
                facts = self._saved_page_facts(chapter_num)
                pages = [
                    {"index": i, "filename": name,
                     "panels": facts.get(name, (0, False))[0],
                     "decided": facts.get(name, (0, False))[1]}
                    for i, name in enumerate(self.page_names(chapter_num), start=1)
                ]
            out.append({
                "chapter": chapter_num,
                "index": index,
                "loaded": state is not None,
                "pages": pages,
                "panels": sum(page["panels"] for page in pages),
                "marked_pages": sum(1 for page in pages if page["panels"]),
                # Pages with nothing on them that nobody has decided about -
                # the work actually left in this chapter. A page MAGI has
                # filled in is not "waiting" even though no person has
                # confirmed it; the sidebar counts the same thing.
                "undecided_pages": sum(1 for page in pages
                                       if not page["decided"] and not page["panels"]),
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
