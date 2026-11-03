"""The marking session's detection queue - mixed into MarkerSession.

Everything MAGI does in a session goes through one queue and one worker
thread. The alternative - each request spawning its own detection - is
several model loads racing for one GPU, and a progress report that can't say
what it is progressing through.

Works on MarkerSession's own state (see its __init__): chapters, index,
read_only, finished, auto_order, auto_save, _states, and the _jobs/_worker/
_active/_run_* fields that belong to this queue."""

from __future__ import annotations

import threading
from typing import Any

from remanga.console import console, escape as _esc


class DetectionQueueMixin:
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
        running. Returns the chapters actually queued. The only way detection
        starts: nothing queues it on its own - see POST /api/detect.

        Never in a read-only session: detection WRITES - it fills `marks` for
        every untouched page - so a viewer opened to check what was actually
        saved would fill up with AI guesses that are in nobody's crops.json.

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

    def queue_remark(self, config, chapters: list[str], pages: list[str] | None = None) -> list[str]:
        """Queues Remark: MAGI detects the pages again and its marks REPLACE
        what is on them, hand-drawn or not (MarkerState.replace_with_detected).
        Returns the chapters queued.

        Always honoured, unlike Detect: a chapter detected earlier this session
        is exactly what someone remarks. Only a remark for the same chapter and
        pages that is still waiting is not queued twice. The browser confirms
        before asking for this - see remark_plan."""
        if self.read_only or not config.magi_enabled:
            return []
        queued: list[str] = []
        with self._jobs_lock:
            self._begin_run_if_idle()
            waiting = {(job["chapter"], tuple(job["pages"] or ())) for job in self._jobs if job["kind"] == "remark"}
            for chapter in chapters:
                if chapter not in self.chapters or (chapter, tuple(pages or ())) in waiting:
                    continue
                self._jobs.append({
                    "kind": "remark", "chapter": chapter, "pages": pages, "force": False, "replace": True,
                })
                self._note_queued("remark", chapter)
                queued.append(chapter)
        if queued:
            self._ensure_worker(config)
        return queued

    def queue_all(self, config) -> list[str]:
        """Every chapter from the one on screen to the end, then the ones
        before it. In that order because "all chapters" is nearly always
        asked while looking at where you stopped - the chapters ahead are
        the ones about to be needed, and the ones behind are usually already
        done."""
        ordered = self.chapters[self.index:] + self.chapters[:self.index]
        return self.queue_detection(config, ordered)

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
                    replace=job.get("replace", False),
                )
                if job["kind"] == "remark" and job["pages"] is None:
                    # A whole chapter has now had a pass; a later Detect over it
                    # has nothing left to fill in.
                    state.detect_started = True
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

    def detection_status(self) -> dict[str, Any]:
        """What the assist card reports: the chapter being detected right
        now, how far in it is, and what's still waiting."""
        with self._jobs_lock:
            queued = [job["chapter"] for job in self._jobs]
            run_total, run_done, last_run = self._run_total, self._run_done, self._last_run
            active, active_kind = self._active, self._active_kind
        state = self._states.get(active) if active else None
        return {
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
        }
