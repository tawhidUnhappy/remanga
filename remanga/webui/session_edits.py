"""Remarking, reordering and the save switches of a marking session - mixed
into MarkerSession.

Works on MarkerSession's own state (see its __init__) and, for what a remark
would replace in chapters not opened yet, on the outline's reading of
crops.json (session_outline.py)."""

from __future__ import annotations

import threading
from typing import Any

from remanga.json_io import has_real_json_content, read_json
from remanga.paths import get_chapter_dir


class MarkEditsMixin:
    # --- remarking ------------------------------------------------------

    def chapter_is_narrated(self, chapter_num: str) -> bool:
        return has_real_json_content(get_chapter_dir(self.project, chapter_num) / "narration.json")

    def _page_marks_now(self, chapter_num: str) -> dict[str, tuple[int, int, bool]]:
        """{filename: (marks, hand-made marks, emptied on purpose)} for every
        page with something to lose - from the session if the chapter has been
        opened, otherwise from its crops.json, without decoding a single image
        (a plan over "all chapters" must not open every page of the project).
        A panel saved before `src` was recorded counts as hand-made: the file
        can't say otherwise, and overstating what a remark replaces is the
        safe direction to be wrong in."""
        state = self._states.get(chapter_num)
        if state is not None:
            with state.lock:
                return {
                    page["filename"]: (
                        len(state.marks.get(page["filename"]) or []),
                        sum(1 for m in state.marks.get(page["filename"]) or [] if m.get("src") != "ai"),
                        page["filename"] in state.decided,
                    )
                    for page in state.pages
                }
        crops_path = get_chapter_dir(self.project, chapter_num) / "crops.json"
        if not has_real_json_content(crops_path):
            return {}
        try:
            entries = read_json(crops_path).get("pages", [])
        except Exception:
            return {}
        facts = self._saved_page_facts(chapter_num)
        out: dict[str, tuple[int, int, bool]] = {}
        for entry in entries:
            filename = entry.get("page_filename")
            panels = entry.get("panels") or []
            decided = facts.get(filename, (0, False))[1]
            out[filename] = (len(panels), sum(1 for panel in panels if panel.get("src") != "ai"), decided)
        return out

    def remark_plan(self, chapters: list[str], pages: list[str] | None = None) -> dict[str, Any]:
        """What a Remark over `chapters` (only `pages` of them, if given) would
        replace, without doing any of it - the numbers the browser's confirm
        states before anything is lost: how many pages, how many of those have
        marks now and how many have marks someone drew or edited, how many were
        emptied on purpose, and which chapters already have narration (their
        panel ids can change under it)."""
        wanted = set(chapters)
        targets = [c for c in self.chapters if c in wanted]
        total = marked = hand_made = emptied = 0
        for chapter in targets:
            names = pages if pages is not None else self.page_names(chapter)
            facts = self._page_marks_now(chapter)
            total += len(names)
            for name in names:
                count, manual, decided = facts.get(name, (0, 0, False))
                marked += count > 0
                hand_made += manual > 0
                emptied += decided and count == 0
        return {
            "chapters": targets,
            "pages": total,
            "marked": marked,
            "hand_made": hand_made,
            "emptied": emptied,
            "narrated": [c for c in targets if self.chapter_is_narrated(c)],
        }

    # --- reading order --------------------------------------------------

    def reorder(self, chapters: list[str], pages: list[str] | None = None) -> dict[str, int]:
        """Puts marks into reading order over `chapters` (only `pages` of them,
        if given), right now, in the calling thread. Returns {chapter: pages
        whose order changed}.

        Not queued behind detection. Reorder needs no GPU and takes
        milliseconds, but a Detect over all chapters can leave the queue hours
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

    # --- saving ---------------------------------------------------------

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
