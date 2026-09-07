"""Choosing chapters - one, or several.

Both pickers list what the project actually has, each row carrying that
chapter's production status, so picking a chapter to work on and seeing how
far it got are the same screen. Typing a chapter number that doesn't exist
yet is still possible (that's how a new chapter starts), but it's the
explicit "New chapter…" row rather than the default path - pre-filled with
the first chapter MangaDex lists that this project doesn't have, not with
"one more than the newest one here"; see suggest_next_chapter for why those
are not the same number."""

from __future__ import annotations

import time
from typing import Any, List, NamedTuple, Optional, Sequence

from remanga.console import console
from remanga.full_recap import chapter_sort_key, discover_chapters
from remanga.status import get_chapter_status
from remanga.tui import CANCEL, Choice, ask_text, is_cancel, multiselect, select

_NEW = "__new_chapter__"


class ChapterSuggestion(NamedTuple):
    """What to pre-fill "New chapter…" with, and where that number came
    from. The origin travels with the number because the two answers below
    are worth very different amounts of trust - "MangaDex lists this one and
    you don't have it" is a fact, "one past your newest" is a guess - and a
    pre-filled box that doesn't say which one it is invites accepting the
    guess as though it were the fact."""

    number: str
    origin: str


def chapter_choices(project_name: str, chapters: Optional[Sequence[str]] = None) -> List[Choice]:
    listing = list(chapters) if chapters is not None else discover_chapters(project_name)
    return [
        Choice(label=f"Chapter {chapter}",
               hint=get_chapter_status(project_name, chapter)["summary"],
               value=chapter)
        for chapter in listing
    ]


def _numeric_successor(chapters: Sequence[str]) -> str:
    """One past the highest numeric chapter in `chapters`, or "1" for none -
    the last-resort guess when MangaDex's own list can't be consulted. Only
    ever right for a manga numbered in whole steps: a project sitting on
    4.1 gets "5.1" out of this, which is why it is the fallback and not the
    answer (see suggest_next_chapter)."""
    numbers = []
    for chapter in chapters:
        try:
            numbers.append(float(chapter))
        except ValueError:
            continue
    if not numbers:
        return "1"
    nxt = max(numbers) + 1
    return str(int(nxt)) if float(nxt).is_integer() else str(nxt)


def _numbers_of(entries: Sequence[dict]) -> List[str]:
    return [str(entry["chapter"]) for entry in entries if entry.get("chapter")]


def _remote_chapter_numbers(project_name: str) -> List[str]:
    """Every chapter number MangaDex lists for this project's manga, in
    reading order - from the same cached feed the download picker reads,
    under the same 24h freshness rule (downloader/mangadex.py's
    CHAPTER_LIST_CACHE_TTL_SECONDS, imported rather than restated so the two
    screens can never disagree about what upstream has).

    A fresh cache is answered from manifest.json with no network at all,
    which is what keeps this affordable in a function that runs every time
    a chapter picker opens. A missing or expired one is fetched: without
    that, "the next chapter" would be answered from a listing taken before
    the chapter in question was published, which is the same wrong answer
    as not asking MangaDex at all, just harder to notice.

    Falls back, in order: stale cache (a listing from yesterday still beats
    guessing) -> empty. Empty for a project with no saved manga source, or
    when MangaDex can't be reached at all - a pre-filled suggestion is
    never worth failing a menu over, and suggest_next_chapter counts
    instead."""
    # Deferred, like reset/actions.py's: importing the downloader at module
    # scope would drag config + requests into every wizard screen that only
    # wants to list chapter folders.
    from remanga.downloader.mangadex import CHAPTER_LIST_CACHE_TTL_SECONDS
    from remanga.paths import load_project_metadata, read_remote_chapter_cache

    cached = read_remote_chapter_cache(project_name)
    entries = cached.get("chapters") or []
    if entries and (time.time() - cached.get("fetched_at", 0)) < CHAPTER_LIST_CACHE_TTL_SECONDS:
        return _numbers_of(entries)

    meta = load_project_metadata(project_name)
    if not (meta.get("manga_url") or meta.get("manga_id")):
        return _numbers_of(entries)

    from remanga.config import RemangaConfig
    from remanga.downloader import MangaDexDownloader

    console.print("[dim]Checking MangaDex's chapter list for the next chapter...[/]")
    try:
        fetched = MangaDexDownloader(RemangaConfig.load().downloader).list_chapters_with_status(
            project_name
        )
    except Exception as e:
        console.print(
            f"[dim]Couldn't reach MangaDex ({e}) - "
            f"{'using the last list fetched' if entries else 'suggesting from what is on disk'}.[/]"
        )
        return _numbers_of(entries)
    return _numbers_of(fetched)


def suggest_next_chapter(project_name: str) -> ChapterSuggestion:
    """The chapter to pre-fill "New chapter…" with: the FIRST chapter
    MangaDex lists that this project doesn't already have a folder for.

    Asking MangaDex rather than adding one to the newest local chapter is
    the whole point. A manga numbered 1, 2.1, 2.2, 3.1, 3.2, 4.1 has 4.2
    next, not 5.1; one with a 12.5 bonus chapter has 12.5 next, not 13; and
    a project missing chapter 7 out of 1-10 is missing 7, not 11. Counting
    can only ever be right for whole-number-numbered manga with no gaps,
    and it is silently wrong - a plausible number that simply doesn't exist
    upstream - for every other case, which is exactly the kind of wrong
    answer a pre-filled box gets accepted as correct.

    Comparison is by chapter_sort_key, not by string, so a folder saved as
    "01" is recognised as MangaDex's "1" instead of suggesting a chapter
    that is already downloaded under a differently-formatted name.

    Falls back to _numeric_successor when MangaDex can't be consulted, and
    when it can but every chapter it lists is already here - in both cases
    saying so in `origin`, since neither is a number MangaDex confirmed."""
    local = discover_chapters(project_name)
    have = {chapter_sort_key(chapter) for chapter in local}

    remote = _remote_chapter_numbers(project_name)
    for chapter in remote:
        if chapter_sort_key(chapter) not in have:
            return ChapterSuggestion(chapter, "first chapter on MangaDex this project doesn't have")

    guess = _numeric_successor(local)
    if remote:
        return ChapterSuggestion(
            guess, "you already have every chapter MangaDex lists - refetch the list if a new one is out",
        )
    return ChapterSuggestion(guess, "one past your newest - MangaDex's chapter list wasn't available")


def select_chapter(project_name: str, *, title: str = "Chapter") -> Any:
    """One chapter. Returns its number as a string, or CANCEL."""
    rows = chapter_choices(project_name)
    suggestion = suggest_next_chapter(project_name)
    rows.append(Choice(label="New chapter…", hint=f"suggests {suggestion.number} · {suggestion.origin}",
                       value=_NEW))

    picked = select(title, rows, default=rows[-2].value if len(rows) > 1 else None,
                    note=f"{len(rows) - 1} chapter(s) in this project")
    if is_cancel(picked):
        return CANCEL
    if picked != _NEW:
        return picked

    return ask_text("Chapter number", default=suggestion.number, allow_empty=False,
                    note=f"{suggestion.origin} · type any other, e.g. 12.5 for a bonus chapter")


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
