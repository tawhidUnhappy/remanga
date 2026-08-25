"""Chapter reset: wipe generated production artifacts while preserving downloaded pages."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from remanga.console import console
from remanga.paths import get_chapter_dir

# Chapter-workspace entries that represent the downloaded source pages — always preserved on restart.
KEEP_ON_RESTART = {"pages", "pages.zip", "pages_metadata.json"}

# A "marks_only" restart additionally keeps crops.json — the panel coordinates
# marked by hand in the panel-marking web UI — but drops everything derived
# from it: panels/, sheets/, the vision zip, and narration.json all get
# wiped and rebuilt from crops.json on the next run. Useful when the marks
# are still good but a cropper setting changed (margin, gutter-snap, vision
# packaging format, ...) or the narration script needs a clean redo.
KEEP_ON_MARKS_ONLY_RESTART = KEEP_ON_RESTART | {"crops.json"}

# A "soft" restart additionally keeps everything upstream of TTS: crops.json
# (the marked panel coordinates), panels/ (the actual cropped panel image
# files), panels_manifest.json (crop.py's own bookkeeping for that folder),
# and narration.json (the LLM-written script). That's the expensive-to-redo
# work — marking every panel by hand and writing a whole chapter's narration
# — so it lets voice/BGM/resolution/vision-format settings change and
# TTS/mix/render redo cleanly without re-marking or re-narrating anything.
# Sheets/the vision zip/audio/video still get wiped, same as a hard restart.
KEEP_ON_SOFT_RESTART = KEEP_ON_RESTART | {"crops.json", "panels", "panels_manifest.json", "narration.json"}

RESTART_MODES = ("hard", "marks_only", "soft")


def _keep_set(mode: str) -> set:
    if mode == "hard":
        return KEEP_ON_RESTART
    if mode == "marks_only":
        return KEEP_ON_MARKS_ONLY_RESTART
    if mode == "soft":
        return KEEP_ON_SOFT_RESTART
    raise ValueError(f"Unknown restart mode {mode!r} - expected one of {RESTART_MODES}")


def restart_candidates(project_name: str, chapter_num: str, *, mode: str = "hard") -> List[Path]:
    """Lists everything in the chapter workspace a restart of this `mode` would delete
    (before any narration.json re-emptying a marks_only restart also does - see
    restart_chapter), without deleting it."""
    chap_dir = get_chapter_dir(project_name, chapter_num)
    if not chap_dir.exists():
        return []
    keep = _keep_set(mode)
    return [entry for entry in sorted(chap_dir.iterdir()) if entry.name not in keep]


def restart_chapter(
    project_name: str,
    chapter_num: str,
    *,
    mode: str = "hard",
    reverify_downloads: bool = True,
) -> List[Path]:
    """
    Deletes generated chapter artifacts while preserving the downloaded pages/ folder,
    pages.zip, and pages_metadata.json — so the chapter can be reprocessed without
    re-downloading. Three levels, from most to least destructive:

    - "hard" (default, the original restart behavior): wipes everything else -
      crops.json, panels/, sheets/, the vision zip, narration.json, audio/,
      audio_timing.json, master_audio*.wav, video/, and the final recap mp4.
    - "marks_only": also keeps crops.json (see KEEP_ON_MARKS_ONLY_RESTART), but
      still wipes narration.json along with everything else - and then
      recreates it as an empty placeholder (the same blank-file state it's in
      before any LLM has ever touched it - see json_io.has_real_json_content),
      so it reads as "not yet generated" rather than just missing.
    - "soft": also keeps crops.json, panels/, panels_manifest.json, and
      narration.json (see KEEP_ON_SOFT_RESTART) - only sheets/the vision
      zip/audio/video get wiped.

    reverify_downloads (on by default, every mode) re-runs the normal download
    step's own presence/integrity check against pages/ afterward — re-fetching
    anything missing or left at 0 bytes — using the manga URL/ID already saved for
    this project, no re-entry needed. A failure there (e.g. no network right now)
    is reported but doesn't undo the deletion that already succeeded.

    Returns the paths that were removed.
    """
    candidates = restart_candidates(project_name, chapter_num, mode=mode)
    for entry in candidates:
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    if mode == "marks_only":
        (get_chapter_dir(project_name, chapter_num) / "narration.json").write_text("", encoding="utf-8")

    if reverify_downloads:
        _reverify_downloads(project_name, chapter_num)

    return candidates


def _reverify_downloads(project_name: str, chapter_num: str) -> None:
    """Re-checks (and re-fetches if needed) this chapter's downloaded pages, the same
    way every normal pipeline run's own download step already does — deferred imports
    to dodge a config/downloader/reset import cycle, same pattern as
    webui/detection.py's deferred magi_assist import."""
    from remanga.config import RemangaConfig
    from remanga.downloader import MangaDexDownloader

    try:
        config = RemangaConfig.load()
        MangaDexDownloader(config.downloader).download_chapter(None, chapter_num, project_name)
    except Exception as e:
        console.print(
            f"[yellow]Restart finished, but re-verifying downloaded pages failed: {e}[/]\n"
            f"[dim]The chapter reset is still in effect - run the download step again when you can.[/]"
        )
