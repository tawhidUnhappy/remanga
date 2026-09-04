"""Chapter reset: wipe generated production artifacts while preserving the
chapter's source folder (or the parts of it each mode keeps).

paths.get_chapter_dir holds ONLY source material - pages/, panels/,
crops.json, narration.json - and everything derived lives one level up
under paths.get_generated_dir's per-kind, per-chapter directories. So every
reset wipes ALL of those generated directories for the chapter, every time:
there's never a reason to leave a stale sheet, zip, audio clip or rendered
frame behind once the source it came from might change. The modes differ
only in how much of the SOURCE folder they keep.

Split by role - `modes` (what each preset keeps, as data), `entries` (what's
on disk / what would be deleted, no deletion), `actions` (the deletions and
their bookkeeping) - so the destructive code is a short file that reads
top to bottom, and the listing used to build a confirmation screen is
provably the same listing the delete loop consumes."""

from __future__ import annotations

from remanga.reset.actions import restart_chapter, reverify_chapter_downloads, wipe_chapter
from remanga.reset.entries import generated_dirs_for_chapter, restart_candidates, wipeable_entries
from remanga.reset.modes import (
    KEEP_ON_MARKS_ONLY_RESTART, KEEP_ON_RESTART, KEEP_ON_SOFT_RESTART, RESTART_MODE_BY_NAME,
    RESTART_MODE_NAMES, RESTART_MODES, RestartMode, keep_set,
)

__all__ = [
    "KEEP_ON_MARKS_ONLY_RESTART",
    "KEEP_ON_RESTART",
    "KEEP_ON_SOFT_RESTART",
    "RESTART_MODES",
    "RESTART_MODE_BY_NAME",
    "RESTART_MODE_NAMES",
    "RestartMode",
    "generated_dirs_for_chapter",
    "keep_set",
    "restart_candidates",
    "restart_chapter",
    "reverify_chapter_downloads",
    "wipe_chapter",
    "wipeable_entries",
]
