"""What each restart mode keeps - the fixed presets, as data.

`restart` offers four named modes and `wipe` offers "keep any combination
you like" (see remanga.reset.entries.wipeable_entries). The four presets
live here as specs rather than as an if/elif chain plus two parallel
dictionaries of display strings in the command handler: the label and the
"kept:" line shown before a destructive confirmation are part of what a
mode *is*, and having them anywhere else is how a mode's description ends
up describing what it used to delete."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

# Chapter-source entries kept by each deletion mode. "pages" (the downloaded
# scans) is always kept - a restart never re-downloads unless
# reverify_downloads finds something missing.
KEEP_ON_RESTART = {"pages"}
KEEP_ON_MARKS_ONLY_RESTART = KEEP_ON_RESTART | {"crops.json"}
KEEP_ON_SOFT_RESTART = KEEP_ON_RESTART | {
    "crops.json", "panels", "narration.json", "narration_review.json", "narration_reviews",
}

_KEEP_SETS: Dict[str, set] = {
    "hard": KEEP_ON_RESTART,
    "marks_only": KEEP_ON_MARKS_ONLY_RESTART,
    "soft": KEEP_ON_SOFT_RESTART,
}


@dataclass(frozen=True)
class RestartMode:
    """One selectable restart preset.

    `deletion_mode` is the mode that actually decides what gets deleted, and
    is usually the mode's own name. "remark" is the exception: it deletes
    exactly like marks_only and then reopens the Panel Marker, which is a
    UI behavior rather than a different deletion - expressing that here is
    what stops it from being a special case inside the delete path."""

    name: str
    label: str
    keeps: str
    summary: str
    deletion_mode: str = ""
    reopen_marker: bool = False

    @property
    def deletes_like(self) -> str:
        return self.deletion_mode or self.name


RESTART_MODES: Tuple[RestartMode, ...] = (
    RestartMode(
        "hard", "Hard restart", "downloaded pages",
        "back to just the downloaded pages - re-mark, re-crop, re-narrate",
    ),
    RestartMode(
        "marks_only", "Marks-only restart",
        "downloaded pages and crops.json (narration.json gets emptied, not kept)",
        "keep the panel marks, redo everything after them",
    ),
    RestartMode(
        "remark", "Re-mark restart",
        "downloaded pages and crops.json (narration.json gets emptied, not kept)",
        "same as marks-only, then reopens the Panel Marker with those marks loaded",
        deletion_mode="marks_only", reopen_marker=True,
    ),
    RestartMode(
        "soft", "Soft restart", "downloaded pages, crops.json, panels/, and narration.json",
        "keep everything hand-made; wipe only generated audio/video/packaging",
    ),
)

RESTART_MODE_NAMES = tuple(mode.name for mode in RESTART_MODES)
RESTART_MODE_BY_NAME = {mode.name: mode for mode in RESTART_MODES}


def keep_set(mode: str) -> set:
    """The chapter-source entries a deletion mode preserves. Accepts only
    real deletion modes ("remark" resolves to marks_only before it gets
    here - see RestartMode.deletes_like)."""
    try:
        return set(_KEEP_SETS[mode])
    except KeyError:
        raise ValueError(
            f"Unknown restart mode {mode!r} - expected one of {tuple(_KEEP_SETS)}"
        ) from None
