"""Choosing chapters - one, or several.

Both pickers list what the project actually has, each row carrying that
chapter's production status, so picking a chapter to work on and seeing how
far it got are the same screen. Typing a chapter number that doesn't exist
yet is still possible (that's how a new chapter starts), but it's the
explicit "New chapter…" row rather than the default path."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from remanga.full_recap import chapter_sort_key, discover_chapters
from remanga.status import get_chapter_status
from remanga.tui import CANCEL, Choice, ask_text, is_cancel, multiselect, select

_NEW = "__new_chapter__"


def chapter_choices(project_name: str, chapters: Optional[Sequence[str]] = None) -> List[Choice]:
    listing = list(chapters) if chapters is not None else discover_chapters(project_name)
    return [
        Choice(label=f"Chapter {chapter}",
               hint=get_chapter_status(project_name, chapter)["summary"],
               value=chapter)
        for chapter in listing
    ]


def next_chapter_number(project_name: str) -> str:
    """The number a new chapter most likely has: one past the highest
    numeric chapter already downloaded, or 1 for an empty project. Derived
    from disk rather than asked, so the common case (working through a manga
    in order) is a pre-filled answer."""
    numbers = []
    for chapter in discover_chapters(project_name):
        try:
            numbers.append(float(chapter))
        except ValueError:
            continue
    if not numbers:
        return "1"
    nxt = max(numbers) + 1
    return str(int(nxt)) if float(nxt).is_integer() else str(nxt)


def select_chapter(project_name: str, *, title: str = "Chapter") -> Any:
    """One chapter. Returns its number as a string, or CANCEL."""
    rows = chapter_choices(project_name)
    suggestion = next_chapter_number(project_name)
    rows.append(Choice(label="New chapter…", hint=f"suggests {suggestion}", value=_NEW))

    picked = select(title, rows, default=rows[-2].value if len(rows) > 1 else None,
                    note=f"{len(rows) - 1} chapter(s) in this project")
    if is_cancel(picked):
        return CANCEL
    if picked != _NEW:
        return picked

    return ask_text("Chapter number", default=suggestion, allow_empty=False,
                    note="e.g. 1, 01, or 12.5 for a bonus chapter")


def select_chapters(project_name: str, *, title: str = "Chapters",
                    preselected: Optional[Sequence[str]] = None) -> Any:
    """Any number of chapters, as a checklist. Returns a list of chapter
    numbers in reading order (empty means "all of them", which is what every
    caller's `--chapters` flag already means when left unset), or CANCEL."""
    rows = chapter_choices(project_name)
    if not rows:
        return []
    chosen = set(preselected or ())
    for row in rows:
        row.checked = row.value in chosen

    picked = multiselect(title, rows, note="leave everything unchecked for every chapter")
    if is_cancel(picked):
        return CANCEL
    return sorted(picked, key=chapter_sort_key)
