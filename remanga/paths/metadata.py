"""Project-level metadata files: project.json (manga identity/source),
manifest.json (small per-chapter production
bookkeeping), and the project listing the wizard's picker reads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.json_io import read_json_or, write_json

from .projects import get_project_dir, get_projects_dir


def get_project_metadata_path(project_name: str) -> Path:
    return get_project_dir(project_name) / "project.json"


def load_project_metadata(project_name: str) -> dict[str, Any]:
    return read_json_or(get_project_metadata_path(project_name), {})


def chapter_identity_fields(project_name: str, chapter_num: str) -> dict[str, Any]:
    """The project/manga/chapter identity on a PDF's text page.
    `reading_direction` comes from project.json (the wizard derives it from
    MangaDex's original language), defaulting to right to left."""
    meta = load_project_metadata(project_name)
    return {
        "project_name": project_name,
        "manga_name": meta.get("manga_title", ""),
        "manga_url": meta.get("manga_url", ""),
        "chapter": str(chapter_num),
        "reading_direction": meta.get("reading_direction", "right_to_left"),
    }


def save_project_metadata(project_name: str, data: dict[str, Any]) -> None:
    meta_path = get_project_metadata_path(project_name)
    existing = load_project_metadata(project_name)
    existing.update(data)
    write_json(meta_path, existing)


def get_manifest_path(project_name: str) -> Path:
    """{manga}/manifest.json - ONE file for the whole project carrying the
    informational bookkeeping that used to be three separate, never-read-back
    files repeated in every chapter folder (pages_metadata.json,
    panels_manifest.json, chapter_info.json). Keyed by chapter number, one
    section per production stage that wants to record something about a
    chapter (currently "pages" and "panels") - deliberately kept to small
    summary fields only (counts, ids, a timestamp), never a per-item dump.
    A per-panel/per-page listing (path, crop box, width/height, ...) is
    exactly the bloat those three files were replaced to get rid of - that
    detail already lives in full wherever it's actually needed (panels/
    itself, each package format's own per-part manifest), so repeating it
    here a second time just to sit unread would recreate the same problem
    under a new filename. If a future caller genuinely needs per-item data
    back, resist the urge to reach for this file - it means the caller
    should read the real source (panels/, pages/) instead."""
    return get_project_dir(project_name) / "manifest.json"


def read_manifest(project_name: str) -> dict[str, Any]:
    return read_json_or(get_manifest_path(project_name), {"chapters": {}})


def read_remote_chapter_cache(project_name: str) -> dict[str, Any]:
    """manifest.json['remote_chapters'] - the last MangaDex chapter-feed
    fetch for this project, cached whole (not merged into the per-chapter
    "chapters" sections above, which only ever describe chapters this
    project has actually started downloading): {"manga_id", "fetched_at"
    (epoch seconds), "chapters": [{"chapter", "chapter_id", "pages"}, ...]}.
    Empty dict when nothing's been fetched yet. See
    downloader/chapter_list.py:list_chapters_with_status for the 24h TTL this
    backs and the interactive "refetch" escape hatch."""
    return read_manifest(project_name).get("remote_chapters", {})


def write_remote_chapter_cache(
    project_name: str, manga_id: str, chapters: list[dict[str, Any]], fetched_at: float
) -> None:
    manifest = read_manifest(project_name)
    manifest["remote_chapters"] = {"manga_id": manga_id, "fetched_at": fetched_at, "chapters": chapters}
    write_json(get_manifest_path(project_name), manifest)


def update_manifest_chapter(project_name: str, chapter_num: str, section: str, data: Any) -> None:
    """Read-modify-write manifest.json['chapters'][chapter_num][section] = data.
    Chapters/sections are independent - downloader writes "pages" (called
    once per chapter) - each stage only ever rewrites its own section."""
    manifest = read_manifest(project_name)
    manifest.setdefault("chapters", {}).setdefault(str(chapter_num), {})[section] = data
    write_json(get_manifest_path(project_name), manifest)


def list_projects() -> list[dict[str, Any]]:
    root = get_projects_dir()
    results = []
    if not root.exists():
        return results

    # Case-insensitive so e.g. "reincarnated..." (lowercase r) doesn't sort
    # after every capitalized project name - plain sorted() on Path objects
    # is ASCII/case-sensitive, which reads as a scrambled, seemingly
    # unstable order to anyone not thinking in ASCII code points.
    for p in sorted(root.iterdir(), key=lambda entry: entry.name.casefold()):
        if p.is_dir():
            meta = load_project_metadata(p.name)
            chapters_dir = p / "chapters"
            chapters = []
            if chapters_dir.exists():
                for c in sorted(chapters_dir.iterdir()):
                    if c.is_dir() and c.name.startswith("chapter_"):
                        ch_num = c.name.replace("chapter_", "")
                        chapters.append(ch_num)
            results.append({
                "name": p.name,
                "path": p,
                "manga_url": meta.get("manga_url", ""),
                "manga_id": meta.get("manga_id", ""),
                "last_chapter": meta.get("last_chapter", ""),
                "chapters": chapters,
            })
    return results
