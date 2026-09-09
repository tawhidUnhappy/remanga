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
from remanga.json_io import write_json
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

    def __init__(self, project_name: str, chapters: list[str]):
        self.project = project_name
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
        self.saved: list[Path] = []
        self.finished = threading.Event()

    @property
    def chapter_num(self) -> str:
        return self.chapters[self.index]

    @property
    def current(self) -> MarkerState:
        """This chapter's state, built the first time it's asked for and kept
        afterwards - so going back to chapter 3 to check a mark shows the
        marks you made this session, not a re-read of what's on disk."""
        state = self._states.get(self.chapter_num)
        if state is None:
            state = MarkerState(get_chapter_dir(self.project, self.chapter_num), self.chapter_num)
            self._states[self.chapter_num] = state
        return state

    @property
    def has_next(self) -> bool:
        return self.index + 1 < len(self.chapters)

    def save_current(self) -> Path:
        """Writes the current chapter's crops.json and says so. Called on
        every chapter change, not only at the end: leaving a chapter is the
        moment its marks stop being visible, so it's the moment they have to
        be on disk rather than only in this process's memory."""
        state = self.current
        crops = state.build_crops_json()
        crops_path = state.chapter_dir / "crops.json"
        write_json(crops_path, crops)
        total_panels = sum(len(page["panels"]) for page in crops["pages"])
        console.print(
            f"[bold green]✓ Chapter {_esc(self.chapter_num)}: saved {total_panels} marked panel(s) "
            f"across {len(crops['pages'])} page(s) to:[/] {_esc(str(crops_path))}"
        )
        if crops_path not in self.saved:
            self.saved.append(crops_path)
        return crops_path

    def goto(self, index: int, *, save: bool = True) -> bool:
        """Moves to another chapter in the list, saving the one being left.
        False for an index that isn't a chapter in this session.

        `save=False` is for the one caller that has already written the
        current chapter itself (/api/finish, which saves and then advances) -
        without it that chapter's crops.json would be written twice in a
        row, and the terminal would report the same save twice."""
        if not 0 <= index < len(self.chapters):
            return False
        if index != self.index:
            if save:
                self.save_current()
            self.index = index
        return True

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
        }
