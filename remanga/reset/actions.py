"""The deletions themselves: restart (fixed presets) and wipe (keep any
combination), plus the shared post-delete bookkeeping both need."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from remanga.console import console
from remanga.json_io import write_json
from remanga.paths import get_chapter_dir, get_manifest_path, read_manifest
from remanga.reset.entries import restart_candidates, wipeable_entries


def _delete_all(entries: List[Path]) -> None:
    for entry in entries:
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _clear_panels_manifest(project_name: str, chapter_num: str) -> None:
    """This chapter's "panels" bookkeeping in the shared manifest.json
    describes panel files that no longer exist once panels/ is gone, so it's
    cleared rather than left stale."""
    manifest = read_manifest(project_name)
    chapter_entry = manifest.get("chapters", {}).get(str(chapter_num))
    if chapter_entry and "panels" in chapter_entry:
        del chapter_entry["panels"]
        write_json(get_manifest_path(project_name), manifest)


def restart_chapter(
    project_name: str,
    chapter_num: str,
    *,
    mode: str = "hard",
    reverify_downloads: bool = True,
) -> List[Path]:
    """Deletes generated chapter artifacts while preserving the source folder
    (or the part of it the mode keeps) - see remanga.reset.modes for what
    each mode keeps. Every mode wipes every generated {manga}/{kind}/
    chapter_N/ directory in full: everything in them is cheaply rebuilt from
    whatever source the chosen mode kept.

    A "marks_only" restart additionally recreates narration.json as an empty
    placeholder, so it reads as "not yet generated" rather than missing.

    `reverify_downloads` (on by default) re-runs the normal download step's
    presence/integrity check against pages/ afterward, re-fetching anything
    missing or 0 bytes, using the manga URL/ID already saved for this
    project. A failure there (no network right now) is reported but doesn't
    undo the deletion that already succeeded.

    Returns the paths that were removed."""
    candidates = restart_candidates(project_name, chapter_num, mode=mode)
    _delete_all(candidates)

    if mode == "marks_only":
        (get_chapter_dir(project_name, chapter_num) / "narration.json").write_text("", encoding="utf-8")

    _clear_panels_manifest(project_name, chapter_num)

    if reverify_downloads:
        reverify_chapter_downloads(project_name, chapter_num)

    return candidates


def wipe_chapter(
    project_name: str, chapter_num: str, keep_names: set, *, reverify_downloads: bool = True,
) -> List[Path]:
    """Deletes every entry from wipeable_entries() whose name isn't in
    `keep_names` - the fully dynamic counterpart to the fixed restart modes,
    letting a caller keep any combination at all (e.g. keep video/ and
    narration.json but wipe panels/ to re-crop with new settings, which none
    of the presets can express).

    `reverify_downloads` behaves exactly like restart_chapter's flag -
    re-checks/re-fetches pages/ afterward regardless of whether pages/ was
    kept or wiped, so a wipe that deleted it ends up re-downloaded rather
    than just missing. Returns the paths that were removed."""
    candidates = [e for e in wipeable_entries(project_name, chapter_num) if e.name not in keep_names]
    _delete_all(candidates)

    if "panels" not in keep_names:
        _clear_panels_manifest(project_name, chapter_num)

    if reverify_downloads:
        reverify_chapter_downloads(project_name, chapter_num)

    return candidates


def reverify_chapter_downloads(project_name: str, chapter_num: str) -> None:
    """Re-checks (and re-fetches if needed) this chapter's downloaded pages,
    exactly the way every normal pipeline run's download step already does.
    Deferred imports dodge a config/downloader/reset import cycle, the same
    pattern webui/detection.py uses for its magi_assist import."""
    from remanga.config import RemangaConfig
    from remanga.downloader import MangaDexDownloader

    try:
        config = RemangaConfig.load()
        MangaDexDownloader(config.downloader).download_chapter(None, chapter_num, project_name)
    except Exception as e:
        console.print(
            f"[yellow]Reset finished, but re-verifying downloaded pages failed: {e}[/]\n"
            f"[dim]The chapter reset is still in effect - run the download step again when you can.[/]"
        )
