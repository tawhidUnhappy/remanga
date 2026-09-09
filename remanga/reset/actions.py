"""The deletions themselves: restart (fixed presets), wipe (keep any
combination) and wipe_project (the whole project at once), plus the shared
post-delete bookkeeping they need."""

from __future__ import annotations

import shutil
from pathlib import Path

from remanga.console import console
from remanga.json_io import write_json
from remanga.paths import get_chapter_dir, get_manifest_path, read_manifest
from remanga.reset.entries import (
    derived_wipe_candidates,
    project_wipe_candidates,
    restart_candidates,
    wipeable_entries,
)


def _delete_all(entries: list[Path]) -> None:
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
) -> list[Path]:
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
) -> list[Path]:
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


def wipe_project(project_name: str) -> list[Path]:
    """Deletes every generated artifact in the whole project in one sweep -
    audio/, video/, panels_zip/ and every other directory under
    projects/{manga}/ - keeping only PROJECT_KEEP (chapters/ and the
    project's own metadata files). Returns the paths that were removed.

    Not expressible as a loop of wipe_chapter over every chapter, which is
    why it exists: wipe_chapter only ever looks at directories named after
    one chapter, so a "start completely clean" built out of it leaves behind
    everything that isn't filed under a chapter in the run - the full-recap
    join's own _work/ (a half-gigabyte master WAV and a concat list, both
    pointing at frames that are about to be deleted) and its finished MP4,
    the artifact directories of chapters not included this time, and any
    directory from a kind or a layout that isn't produced any more. Those
    are precisely the stale files a regenerate is run to get rid of.

    Downloads are deliberately NOT re-verified here, unlike wipe_chapter:
    pages/ lives inside chapters/ and is never touched by this, and a
    caller rebuilding several chapters re-verifies each one as it reaches
    it (see full_recap.FullRecapCompiler._ensure_chapter_video) rather than
    paying for a whole project's worth of MangaDex checks up front."""
    candidates = project_wipe_candidates(project_name)
    _delete_all(candidates)
    return candidates


def wipe_derived_audio_and_video(project_name: str) -> list[Path]:
    """Deletes everything made FROM the narration, and nothing that made it.

    The fast half of a regenerate. `audio/` - the raw synthesized speech,
    minutes of GPU time per chapter - is kept, and audio_modified/ and
    video/ go. That covers every setting a person actually iterates on:
    voice warmth, ducking, music, levels, resolution, framing. Re-running
    after this rebuilds in seconds what a full regenerate would spend a TTS
    pass on.

    Use wipe_project instead when the narration itself is wrong - a voice
    change, a different engine, or edited narration.json."""
    candidates = derived_wipe_candidates(project_name)
    _delete_all(candidates)
    return candidates


def reverify_chapter_downloads(project_name: str, chapter_num: str) -> None:
    """Re-checks (and re-fetches if needed) this chapter's downloaded pages,
    exactly the way every normal pipeline run's download step already does.
    Called by both chapter resets above and by a regenerate-all compile, so
    its failure message says what is true for all of them - the pages
    already on disk are left alone - rather than naming any one of them.
    Deferred imports dodge a config/downloader/reset import cycle, the same
    pattern webui/detection.py uses for its magi_assist import."""
    from remanga.config import RemangaConfig
    from remanga.downloader import MangaDexDownloader

    try:
        config = RemangaConfig.load()
        MangaDexDownloader(config.downloader).download_chapter(None, chapter_num, project_name)
    except Exception as e:
        console.print(
            f"[yellow]Couldn't re-verify chapter {chapter_num}'s downloaded pages: {e}[/]\n"
            f"[dim]The pages already on disk are untouched - run the download step again when you can.[/]"
        )
