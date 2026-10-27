"""Which source plug-ins a manga comes from (remanga/plugins/, kind "source"),
and their clients.

A project can have several sources (user request, 2026-10-24): the same manga
on MangaDex and on comix.to, say, where MangaDex only links to the licensed
chapters and comix.to has their pages. project.json keeps them in order of
preference:

    "sources": [{"source": "mangadex", "manga_id": "...", "manga_url": "..."},
                {"source": "comix", "manga_id": "6dq7g", "manga_url": "https://comix.to/title/..."}]

The top-level "source"/"manga_id"/"manga_url" stay the first (primary) one's,
so a project with one source - every project made before this - has no list
at all and reads exactly as it did. A project made before sources were
plug-ins has no "source" either: the default one (MangaDex).

Which source a chapter comes from: the one that downloaded it, while the
project still has that source; otherwise the first one listing it with pages
(MangaDex lists a licensed chapter with none). Clients never decide this -
they are always handed their own manga's link.
"""

from __future__ import annotations

from typing import Any

from remanga import plugins
from remanga.chapters import chapter_key, chapter_sort_key
from remanga.console import console, escape as _esc
from remanga.json_io import write_json
from remanga.paths import get_project_metadata_path, load_project_metadata, read_manifest

IDENTITY = ("source", "manga_id", "manga_url")


def source_for(reference: str) -> plugins.Source:
    """The source whose link or ID this is - the default one for anything no
    source claims (a title to search)."""
    every = plugins.items("source")
    for source in every:
        if plugins.call(source.handles, reference):
            return source
    return every[0]


def _entries(meta: dict[str, Any]) -> list[dict[str, str]]:
    """project.json's sources, first = preferred: its list, or the one
    source of a project that has no list."""
    listed = [dict(entry) for entry in meta.get("sources") or [] if entry.get("source")]
    if listed:
        return listed
    name = meta.get("source") or plugins.items("source")[0].name
    return [{"source": name, "manga_id": meta.get("manga_id", ""), "manga_url": meta.get("manga_url", "")}]


def project_entries(project: str) -> list[dict[str, str]]:
    return _entries(load_project_metadata(project))


def project_source(project: str) -> plugins.Source:
    """The project's first (preferred) source."""
    return plugins.get("source", project_entries(project)[0]["source"])


def project_sources(project: str) -> list[tuple[plugins.Source, dict[str, str]]]:
    """Each of the project's sources with its entry, in order of preference.
    One whose plug-in is not installed is left out."""
    found = [(plugins.find("source", entry["source"]), entry) for entry in project_entries(project)]
    return [(source, entry) for source, entry in found if source is not None]


def client(source: plugins.Source, config) -> Any:
    """The source's client, built with the downloader settings."""
    return plugins.resolve(source.client)(config.downloader)


def project_client(project: str, config) -> Any:
    return client(project_source(project), config)


def _save(project: str, entries: list[dict[str, str]]) -> None:
    """The list, and the first entry as the top-level identity. One source
    is kept without a list, as projects always were."""
    meta = load_project_metadata(project)
    meta.update({key: entries[0].get(key, "") for key in IDENTITY})
    if len(entries) > 1:
        meta["sources"] = entries
    else:
        meta.pop("sources", None)
    write_json(get_project_metadata_path(project), meta)


def remember_source(project: str, name: str, manga_id: str, manga_url: str) -> None:
    """What a client records after reading or downloading its manga: that
    source's id and link. Only that source's entry changes - before projects
    had several, a client wrote the top-level identity, which on a project
    with two sources would hand the other source's chapters this one's id."""
    meta = load_project_metadata(project)
    entries = _entries(meta)
    for entry in entries:
        if entry["source"] == name:
            entry.update(manga_id=manga_id, manga_url=manga_url)
            break
    else:
        if meta.get("sources"):
            entries.append({"source": name, "manga_id": manga_id, "manga_url": manga_url})
        else:  # a single-source project switching source by a download with a link, as before
            entries = [{"source": name, "manga_id": manga_id, "manga_url": manga_url}]
    _save(project, entries)


def add_source(project: str, reference: str, config) -> dict[str, str]:
    """Adds the manga at `reference` (a link or ID) as another source of the
    project, after the ones it has. The same source twice replaces its
    entry: one manga per source."""
    source = source_for(reference)
    if not plugins.call(source.handles, reference):
        raise ValueError(f"'{reference}' is not a link or ID any source knows - a title can't be added as a source.")
    manga_id = client(source, config).parse_manga_id(reference)
    entry = {"source": source.name, "manga_id": manga_id, "manga_url": reference.strip()}
    entries = [e for e in project_entries(project) if e["source"] != source.name]
    replaced = len(entries) < len(project_entries(project))
    entries.append(entry)
    _save(project, entries)
    console.print(f"[green]✓ {'Replaced' if replaced else 'Added'} source {_esc(source.display_name)}[/] "
                  f"[dim]({_esc(manga_id)})[/] - {len(entries)} source(s)")
    return entry


def remove_source(project: str, name: str) -> None:
    entries = project_entries(project)
    kept = [e for e in entries if e["source"] != name]
    if len(kept) == len(entries):
        raise ValueError(f"This project has no source '{name}' - it has {', '.join(e['source'] for e in entries)}.")
    if not kept:
        raise ValueError("That is the project's only source - a project needs one.")
    _save(project, kept)


def _downloaded_by(project: str) -> dict[str, str]:
    """chapter key -> the source that downloaded its pages (manifest.json)."""
    chapters = read_manifest(project).get("chapters", {})
    return {chapter_key(ch): (data.get("pages") or {}).get("source") or "mangadex"
            for ch, data in chapters.items() if data.get("pages")}


def _has_pages(row: dict[str, Any]) -> bool:
    return row.get("pages") is None or bool(row.get("pages"))


def chapter_listing(project: str, config, refresh: bool | None = None,
                    url: str | None = None) -> list[dict[str, Any]]:
    """Every chapter the project's sources list, one row per chapter with its
    local status and "source" (the plug-in name it comes from).

    `refresh`: True asks every source again, False none; None (opening a
    list) lets each source decide - MangaDex is asked again, a site read
    through Firefox shows its saved list. `url` lists only that manga.
    A source that can't be reached is said and skipped while another
    answers; with every source failing, the last error is raised."""
    if url:
        source = source_for(url)
        rows = client(source, config).list_chapters_with_status(project, url, force_refresh=bool(refresh))
        return [dict(row, source=source.name) for row in rows]

    per_source: list[tuple[str, list[dict[str, Any]]]] = []
    error: Exception | None = None
    for source, entry in project_sources(project):
        force = source.fresh_on_open if refresh is None else refresh
        try:
            rows = client(source, config).list_chapters_with_status(project, entry["manga_url"] or entry["manga_id"],
                                                                     force_refresh=force)
        except Exception as failure:  # one source down must not hide the others
            error = failure
            console.print(f"[yellow]{_esc(source.display_name)}: couldn't read its chapter list - "
                          f"{_esc(str(failure))}[/]")
            continue
        per_source.append((source.name, rows))
    if not per_source and error is not None:
        raise error
    return merge_listings(per_source, _downloaded_by(project))


def merge_listings(per_source: list[tuple[str, list[dict[str, Any]]]],
                   downloaded_by: dict[str, str]) -> list[dict[str, Any]]:
    """One row per chapter number from several sources' lists (in order of
    preference): the row of the source that downloaded it, else the first
    with pages in the configured language, else the first with pages, else
    the first listing it at all."""
    chosen: dict[str, dict[str, Any]] = {}
    for name, rows in per_source:
        for row in rows:
            key = chapter_key(row["chapter"])
            row = dict(row, source=name)
            have = chosen.get(key)
            if have is None:
                chosen[key] = row
                continue
            if downloaded_by.get(key) == have["source"]:
                continue
            if downloaded_by.get(key) == name or (not _has_pages(have) and _has_pages(row)) or (
                    have.get("fallback") and not row.get("fallback") and _has_pages(row)):
                chosen[key] = row
    return sorted(chosen.values(), key=lambda row: chapter_sort_key(row["chapter"]))


def plan_downloads(project: str, chapters: list[str], config) -> list[tuple[plugins.Source, dict[str, str], list[str]]]:
    """Which source downloads which chapters, in the project's order of
    sources. A chapter goes to the source that downloaded it before, else to
    the first source listing it with pages. A source whose list costs nothing
    (MangaDex's API) is asked; one read through a browser is not opened just
    to plan - it takes whatever the cheap ones don't have, and its own
    download looks each chapter up. A chapter a cheap source has only in a
    fallback language goes to it last, when no other source took it."""
    sources = project_sources(project)
    names = {source.name for source, _ in sources}
    before = _downloaded_by(project)
    todo = {chapter_key(ch): ch for ch in chapters}
    plan: dict[str, list[str]] = {source.name: [] for source, _ in sources}
    fallback: dict[str, str] = {}  # chapter key -> a cheap source with it in another language
    for key, chapter in list(todo.items()):
        if before.get(key) in names:
            plan[before[key]].append(chapter)
            del todo[key]
    for source, entry in sources:
        if not todo:
            break
        if source.fresh_on_open:
            rows = client(source, config).list_chapters_with_status(project, entry["manga_url"] or entry["manga_id"])
            rows = [row for row in rows if _has_pages(row)]
            for row in rows:
                if row.get("fallback"):
                    fallback.setdefault(chapter_key(row["chapter"]), source.name)
            listed = {chapter_key(row["chapter"]) for row in rows if not row.get("fallback")}
            claimed = [key for key in todo if key in listed]
        else:
            claimed = list(todo)
        for key in claimed:
            plan[source.name].append(todo.pop(key))
    for key in [key for key in todo if key in fallback]:
        plan[fallback[key]].append(todo.pop(key))
    if todo:
        raise ValueError(f"No source of this project has chapter {', '.join(todo.values())} with pages.")
    return [(source, entry, sorted(plan[source.name], key=chapter_sort_key))
            for source, entry in sources if plan[source.name]]
