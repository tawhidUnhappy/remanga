"""Chapter reset: wipe generated production artifacts while preserving downloaded pages."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from remanga.paths import get_chapter_dir

# Chapter-workspace entries that represent the downloaded source pages — always preserved on restart.
KEEP_ON_RESTART = {"pages", "pages.zip", "pages_metadata.json"}


def restart_candidates(project_name: str, chapter_num: str) -> List[Path]:
    """Lists everything in the chapter workspace a restart would delete, without deleting it."""
    chap_dir = get_chapter_dir(project_name, chapter_num)
    if not chap_dir.exists():
        return []
    return [entry for entry in sorted(chap_dir.iterdir()) if entry.name not in KEEP_ON_RESTART]


def restart_chapter(project_name: str, chapter_num: str) -> List[Path]:
    """
    Deletes every generated chapter artifact (crops.json, panels/, sheets/, the vision
    zip, narration.json, audio/, audio_timing.json, master_audio*.wav, video/, and the
    final recap mp4) while preserving the downloaded pages/ folder, pages.zip, and
    pages_metadata.json — so the chapter can be reprocessed from scratch without
    re-downloading. Returns the paths that were removed.
    """
    candidates = restart_candidates(project_name, chapter_num)
    for entry in candidates:
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return candidates
