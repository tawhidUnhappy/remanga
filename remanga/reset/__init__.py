"""Chapter reset: wipe generated production artifacts while preserving the
chapter's source folder (or the parts of it each mode keeps).

paths.get_chapter_dir holds ONLY source material - pages/, panels/,
crops.json, narration.json - and everything derived lives one level up
under paths.get_generated_dir's per-kind, per-chapter directories. So every
reset wipes ALL of those generated directories for the chapter, every time:
there's never a reason to leave a stale sheet, zip, audio clip or rendered
frame behind once the source it came from might change. The modes differ
only in how much of the SOURCE folder they keep.

One level up, `wipe_project` does the same thing for a whole project at
once: everything under projects/{manga}/ goes except chapters/ (the source
tree) and the project's own metadata files - see modes.PROJECT_KEEP. It is
not a loop over the per-chapter wipes and can't be: those only ever look
inside directories named after one chapter, so they always leave the
full-recap join's own working files and finished MP4, and the artifacts of
any chapter not in the current run, sitting there stale. That is what
`full-recap --regenerate-all` runs before it rebuilds anything.

Split by role - `modes` (what each preset keeps, as data), `entries` (what's
on disk / what would be deleted, no deletion), `actions` (the deletions and
their bookkeeping) - so the destructive code is a short file that reads
top to bottom, and the listing used to build a confirmation screen is
provably the same listing the delete loop consumes."""

from __future__ import annotations

from remanga.reset.actions import (
    restart_chapter,
    reverify_chapter_downloads,
    wipe_chapter,
    wipe_derived_audio_and_video,
    wipe_project,
    wipe_to_sources,
)
from remanga.reset.entries import (
    derived_wipe_candidates,
    generated_dirs_for_chapter,
    project_wipe_candidates,
    restart_candidates,
    sources_wipe_candidates,
    wipeable_entries,
)
from remanga.reset.modes import (
    DEFAULT_REBUILD_MODE,
    KEEP_ON_MARKS_ONLY_RESTART,
    KEEP_ON_RESTART,
    KEEP_ON_SOFT_RESTART,
    KEEP_ON_SOURCES_REBUILD,
    PROJECT_KEEP,
    REBUILD_MODE_BY_NAME,
    REBUILD_MODE_NAMES,
    REBUILD_MODES,
    RESTART_MODE_BY_NAME,
    RESTART_MODE_NAMES,
    RESTART_MODES,
    RestartMode,
    keep_set,
)

__all__ = [
    "DEFAULT_REBUILD_MODE",
    "KEEP_ON_MARKS_ONLY_RESTART",
    "KEEP_ON_RESTART",
    "KEEP_ON_SOFT_RESTART",
    "KEEP_ON_SOURCES_REBUILD",
    "PROJECT_KEEP",
    "REBUILD_MODES",
    "REBUILD_MODE_BY_NAME",
    "REBUILD_MODE_NAMES",
    "RESTART_MODES",
    "RESTART_MODE_BY_NAME",
    "RESTART_MODE_NAMES",
    "RestartMode",
    "derived_wipe_candidates",
    "generated_dirs_for_chapter",
    "keep_set",
    "project_wipe_candidates",
    "restart_candidates",
    "restart_chapter",
    "reverify_chapter_downloads",
    "sources_wipe_candidates",
    "wipe_chapter",
    "wipe_derived_audio_and_video",
    "wipe_project",
    "wipe_to_sources",
    "wipeable_entries",
]
