"""What an upload set is written from: what the manga is called and who made
it - from the manga's site, because an LLM's memory of a manga's credits is
not to be trusted - and the story, from the narration remanga already has."""

from __future__ import annotations

import json
from typing import Any

from remanga import plugins
from remanga.chapters import chapter_sort_key
from remanga.console import console, escape as _esc
from remanga.json_io import has_real_json_content
from remanga.narration import read_reply, story_lines, story_so_far
from remanga.paths import get_narration_path, load_project_metadata, save_project_metadata


def credits(project: str, config) -> dict[str, Any]:
    """{"title", "english_title", "story": [names], "art": [names]} - asked of
    the project's sources once (the first that can say), then kept in
    project.json. A source that cannot say (a site read through the
    browser) is never opened for it: the credits are then unknown, and the
    description leaves them out."""
    meta = load_project_metadata(project)
    if meta.get("credits"):
        return meta["credits"]
    from remanga.sources import project_sources

    for source, entry in project_sources(project):
        made = plugins.resolve(source.client)
        if not hasattr(made, "get_manga_credits") or not entry.get("manga_id"):
            continue
        try:
            found = made(config.downloader).get_manga_credits(entry["manga_id"])
        except Exception as error:   # the description can do without them
            console.print(f"[yellow]Could not ask {_esc(source.display_name)} who made the manga "
                          f"({_esc(str(error))}).[/]")
            continue
        save_project_metadata(project, {"credits": found})
        return found
    return {"title": meta.get("manga_title", ""), "english_title": "", "story": [], "art": []}


# Skip reasons that say a panel is never a thumbnail. A title page is not
# narrated but is often the best art there is (the cover, in colour).
NOT_STORY = {"credits", "ad", "blank", "duplicate"}


def narration_of(project: str, chapter: str) -> tuple[dict[str, str], set[str], dict | None]:
    """A chapter's narration: {panel id: text} for the panels told, the panels
    it skipped as not story (credits, ads, ...), and its memory."""
    path = get_narration_path(project, chapter)
    if not has_real_json_content(path):
        return {}, set(), None
    try:
        doc, memory = read_reply(path)
    except (json.JSONDecodeError, ValueError, OSError, IndexError):
        return {}, set(), None
    panels = [e for e in (doc.get("panels") if isinstance(doc, dict) else None) or []
              if isinstance(e, dict) and e.get("panel")]
    told = {str(e["panel"]): str(e.get("text") or "").strip() for e in panels if str(e.get("text") or "").strip()}
    return told, {str(e["panel"]) for e in panels if e.get("skip") in NOT_STORY}, memory


def story(project: str, chapters: list[str]) -> dict[str, Any]:
    """The story as the upload PDF tells it: the story so far after the last
    of these chapters (every memory up to it, folded - as lines), how the
    first narrated one begins, the line read over every narrated panel, and
    the panels the narration skipped as not story."""
    lines: dict[str, str] = {}
    not_story: set[str] = set()
    opening, opening_from = "", None
    ordered = sorted(chapters, key=chapter_sort_key)
    for chapter in ordered:
        told, skipped, _ = narration_of(project, chapter)
        lines.update(told)
        not_story |= skipped
        if told and opening_from is None:
            opening, opening_from = " ".join(told.values()), chapter
    folded, memory_from = story_so_far(project, ordered[-1], through=True) if ordered else (None, None)
    return {"memory": story_lines(folded) if folded else None, "memory_from": memory_from, "opening": opening,
            "opening_from": opening_from, "lines": lines, "not_story": not_story}
