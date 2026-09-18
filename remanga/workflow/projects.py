"""Making a project from a MangaDex link, and the manga's own facts.

The project's name comes from the manga's English title and its reading
direction from the original language, so neither is ever typed."""

from __future__ import annotations

import re

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.paths import list_projects, load_project_metadata, save_project_metadata

# MangaDex's originalLanguage -> how that market's comics are read.
READING_DIRECTION_BY_LANGUAGE = {
    "ja": "right_to_left",
    "ko": "left_to_right",
    "zh": "left_to_right",
    "zh-hk": "left_to_right",
    "en": "left_to_right",
}


# Longest folder name made from a title; cut at a word.
PROJECT_NAME_MAX = 40


def project_name_from_title(title: str) -> str:
    """A folder name from a manga's title, in the projects' PascalCase style:
    "I Died Protecting My Comrades..." -> "IDiedProtectingMyComrades...",
    cut at a whole word."""
    words = re.findall(r"[A-Za-z0-9]+", title)
    name = ""
    for word in words:
        piece = word[:1].upper() + word[1:]
        if name and len(name) + len(piece) > PROJECT_NAME_MAX:
            break
        name += piece
    return name or "Manga"


def create_project(source: str, config: RemangaConfig) -> str:
    """A project for the manga at `source` (a MangaDex URL, ID or a title to
    search), named after its English title, with its title, original language
    and reading direction fetched. A manga that already has a project opens
    that project instead. Returns the project's name."""
    from remanga.downloader import MangaDexDownloader

    resolver = MangaDexDownloader(config.downloader).resolver
    manga_id = resolver.parse_manga_id(source)
    for project in list_projects():
        if project["manga_id"] == manga_id:
            console.print(f"[green]You already have this manga:[/] {_esc(project['name'])}")
            return project["name"]

    info = resolver.get_manga_info(manga_id)
    base = project_name_from_title(info["english_title"] or info["title"])
    taken = {project["name"].casefold() for project in list_projects()}
    name, n = base, 2
    while name.casefold() in taken:
        name, n = f"{base}{n}", n + 1
    direction = READING_DIRECTION_BY_LANGUAGE.get(info["original_language"], "right_to_left")
    save_project_metadata(name, {
        "project_name": name,
        "manga_url": source.strip(),
        "manga_id": manga_id,
        "manga_title": info["title"],
        "original_language": info["original_language"],
        "reading_direction": direction,
    })
    console.print(f"[bold green]✓ New project:[/] {_esc(name)}\n"
                  f"  {_esc(info['english_title'] or info['title'])}\n"
                  f"  [dim]reads {direction.replace('_', '-')}"
                  + (f" (original language '{info['original_language']}')" if info["original_language"] else "")
                  + "[/]")
    return name


def settle_reading_direction(project: str) -> str:
    """The manga's reading direction, recorded from MangaDex's original
    language when it isn't yet - right to left when that says nothing."""
    meta = load_project_metadata(project)
    if meta.get("reading_direction"):
        return meta["reading_direction"]
    language = str(meta.get("original_language") or "").lower()
    direction = READING_DIRECTION_BY_LANGUAGE.get(language, "right_to_left")
    save_project_metadata(project, {"reading_direction": direction})
    console.print(f"[dim]Reading direction: {direction.replace('_', '-')}"
                  + (f" (MangaDex original language '{language}')" if language in READING_DIRECTION_BY_LANGUAGE
                     else " (the manga default)") + "[/]")
    return direction
