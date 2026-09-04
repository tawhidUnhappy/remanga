"""Choosing (or creating) the project the rest of the wizard works on, and
settling its reading direction without asking when that's already knowable.

The picker shows every project with what's actually in it - how many
chapters, what manga it points at, how far the newest chapter has got -
because "which project?" is really "which of these was I in the middle
of?", and that's a question a list of bare folder names can't answer."""

from __future__ import annotations

from typing import Any, List, Optional

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.paths import list_projects, load_project_metadata, save_project_metadata
from remanga.settings import run_setup_wizard
from remanga.status import get_chapter_status
from remanga.tui import CANCEL, Choice, ask_text, is_cancel, select

_NEW = "__new__"
_SETTINGS = "__settings__"

# MangaDex's originalLanguage -> how that market's comics are read. Native
# Japanese manga is right-to-left; Korean/Chinese webtoons and everything
# Western are left-to-right. Anything not listed here is genuinely unknown,
# and only then is the user asked.
READING_DIRECTION_BY_LANGUAGE = {
    "ja": "right_to_left",
    "ko": "left_to_right",
    "zh": "left_to_right",
    "zh-hk": "left_to_right",
    "en": "left_to_right",
}


def project_choices() -> List[Choice]:
    """Every project on disk, newest-progress first glance: chapter count,
    saved manga source, and the production state of its latest chapter."""
    rows: List[Choice] = []
    for project in list_projects():
        chapters = project["chapters"]
        source = project["manga_url"] or project["manga_id"] or ""
        parts = [f"{len(chapters)} chapter(s)" if chapters else "no chapters yet"]
        if chapters:
            latest = chapters[-1]
            parts.append(f"ch {latest}: {get_chapter_status(project['name'], latest)['summary']}")
        rows.append(Choice(
            label=project["name"],
            hint=" · ".join(parts),
            detail=source[:100],
            value=project["name"],
        ))
    return rows


def select_or_create_project(config: RemangaConfig) -> Any:
    """Returns the chosen/created project name, or CANCEL if the user quit.
    Guarantees the project has a reading direction recorded before handing
    it back, so no later step has to re-ask."""
    while True:
        rows = project_choices()
        rows.append(Choice(label="New project…", hint="start a new manga", value=_NEW))
        rows.append(Choice(label="Settings", hint="engine, assets, resolution, packaging",
                           value=_SETTINGS))

        picked = select(
            "Project", rows,
            note="pick up where you left off, or start something new",
            back_label="Quit",
        )
        if is_cancel(picked):
            return CANCEL
        if picked == _SETTINGS:
            run_setup_wizard(config)
            continue
        name = create_project() if picked == _NEW else picked
        if is_cancel(name):
            continue
        ensure_reading_direction(name)
        return name


def create_project() -> Any:
    """Asks for a name for a new project. No suggested default: a made-up
    manga title pre-filled in the box is a name someone will accept by
    accident, and the folder it creates then follows the project forever."""
    existing = {p["name"].casefold() for p in list_projects()}

    def validate(raw: str) -> Optional[str]:
        if any(ch in raw for ch in "/\\"):
            return "A project name can't contain / or \\ - it becomes a folder under projects/."
        if raw.casefold() in existing:
            return f"'{raw}' already exists - pick it from the list instead."
        return None

    name = ask_text("New project name", allow_empty=False, validate=validate,
                    note="becomes projects/<name>/ - the manga's own workspace")
    return name or CANCEL


def ensure_reading_direction(project_name: str) -> None:
    """Records how this manga is read, asking only when it can't be worked out.

    Right-to-left is the Japanese-manga convention and left-to-right covers
    manhwa/manhua/webtoons and Western comics. Once a chapter has been
    downloaded, MangaDex has already told us the original language (see
    downloader/resolve.py:get_manga_info), so for the overwhelming majority
    of projects this resolves silently and the question never appears."""
    meta = load_project_metadata(project_name)
    if meta.get("reading_direction"):
        return

    language = str(meta.get("original_language") or "").lower()
    inferred = READING_DIRECTION_BY_LANGUAGE.get(language)
    if inferred:
        save_project_metadata(project_name, {"reading_direction": inferred})
        console.print(
            f"[dim]Reading direction: {inferred.replace('_', '-')} "
            f"(from MangaDex original language '{language}').[/]"
        )
        return

    picked = select(
        "How is this manga read?",
        [
            Choice(label="Right to left", hint="Japanese manga convention", value="right_to_left"),
            Choice(label="Left to right", hint="manhwa, manhua, webtoons, Western comics",
                   value="left_to_right"),
        ],
        default="right_to_left",
        note="asked once per project - downloading a chapter usually answers it automatically",
        # Escapable: this has a sensible default and is re-asked next time,
        # so trapping someone in it (the only question in the wizard with no
        # way back) buys nothing.
        back_label="Ask me later",
    )
    if is_cancel(picked):
        return
    save_project_metadata(project_name, {"reading_direction": picked})
