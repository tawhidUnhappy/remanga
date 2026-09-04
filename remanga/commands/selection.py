"""Turning what a user typed about chapters into an actual list of chapters,
and what they typed about a wipe into an actual keep-set.

Shared by the CLI (where these arrive as `--chapters 1,3,7-9`) and by the
wizard (where they arrive from a checklist) so both ends agree on what
"1,3,7-9" means - including the part that matters: a range only expands
against chapters the project really has."""

from __future__ import annotations

from typing import List, Optional

from remanga.full_recap import chapter_sort_key, discover_chapters

# Applied whenever --keep is left unset entirely (None) - the four things
# most expensive/annoying to redo (a re-download, re-marking panels, and the
# two LLM round-trips: the narration pass and the YouTube metadata written
# from it) survive a wipe by default; everything generated from them
# (panels/, sheets/zips, audio, video) does not. Pass --keep explicitly (a
# comma list, or "none" for an absolute full wipe) to override this.
DEFAULT_WIPE_KEEP = {"pages", "crops.json", "narration.json", "youtube.json"}


def split_chapters(raw: Optional[str]) -> Optional[List[str]]:
    """A plain comma list, deduplicated and sorted in reading order. None
    stays None, which every caller reads as "every chapter"."""
    if not raw:
        return None
    return sorted({c.strip() for c in raw.split(",") if c.strip()}, key=chapter_sort_key)


def parse_chapter_selection(raw: str, project_name: str) -> List[str]:
    """Comma-separated chapter numbers and/or numeric ranges ('N-M') - e.g.
    '1,3,7-9'.

    A range expands only against chapters this project actually has, so
    '1-24' can't manufacture chapter numbers that were never downloaded. A
    plain (non-range) token passes through literally even if it doesn't
    exist yet, matching split_chapters' permissiveness elsewhere - a wipe
    naturally no-ops on one that isn't there."""
    existing = discover_chapters(project_name)
    result: set = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo_s, _, hi_s = token.partition("-")
            try:
                lo, hi = float(lo_s), float(hi_s)
            except ValueError:
                result.add(token)  # a literal label with a dash, not a range
                continue
            for chapter in existing:
                try:
                    value = float(chapter)
                except ValueError:
                    continue
                if lo <= value <= hi:
                    result.add(chapter)
            continue
        result.add(token)
    return sorted(result, key=chapter_sort_key)


def resolve_wipe_keep(keep_raw: Optional[str], project_name: Optional[str] = None) -> set:
    """What a wipe keeps: 'none'/'nothing' -> absolutely everything goes;
    any other value -> that comma list, verbatim.

    Left unset (None) falls back to what this project chose last time
    (remembered in project.json - see settings/project_prefs.py), and only
    then to DEFAULT_WIPE_KEEP. So the second chapter of a project wipes the
    way the first one did, without being asked again."""
    if keep_raw is not None:
        if keep_raw.strip().lower() in ("none", "nothing"):
            return set()
        return {n.strip() for n in keep_raw.split(",") if n.strip()}

    if project_name:
        from remanga.settings.project_prefs import remembered_wipe_keep

        remembered = remembered_wipe_keep(project_name)
        if remembered is not None:
            return remembered
    return set(DEFAULT_WIPE_KEEP)
