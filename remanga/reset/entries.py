"""What's on disk for a chapter, and what a given reset would remove.

Pure listing - nothing here deletes anything. Both destructive commands
build their confirmation screen from these functions, so what the user is
shown before confirming is literally the list that gets passed to the
delete loop."""

from __future__ import annotations

from pathlib import Path
from typing import List

from remanga.paths import GENERATED_KINDS, get_chapter_dir, get_generated_dir
from remanga.reset.modes import keep_set


def generated_dirs_for_chapter(project_name: str, chapter_num: str) -> List[Path]:
    """Every {manga}/{kind}/chapter_N/ directory that currently exists for
    this chapter, across every GENERATED_KINDS - what every restart mode
    wipes in full, regardless of mode."""
    dirs = []
    for kind in GENERATED_KINDS:
        d = get_generated_dir(project_name, kind, chapter_num, create=False)
        if d.exists():
            dirs.append(d)
    return dirs


def restart_candidates(project_name: str, chapter_num: str, *, mode: str = "hard") -> List[Path]:
    """Everything a restart of this `mode` would delete (before the
    narration.json re-emptying a marks_only restart also does - see
    restart_chapter): the not-kept part of the chapter's source folder, plus
    every generated directory this chapter has anything in."""
    chap_dir = get_chapter_dir(project_name, chapter_num)
    keep = keep_set(mode)
    source = [entry for entry in sorted(chap_dir.iterdir()) if entry.name not in keep] if chap_dir.exists() else []
    return source + generated_dirs_for_chapter(project_name, chapter_num)


def wipeable_entries(project_name: str, chapter_num: str) -> List[Path]:
    """Every deletable item for this chapter right now: the chapter's own
    source-folder entries (pages/, crops.json, panels/, narration.json, ...)
    plus every generated {kind}/chapter_N/ directory that currently exists.

    This is the live menu `wipe` picks its keep-list from - unlike the fixed
    restart modes, nothing here is wired in; it's simply "what's actually
    here right now", which is what lets the wizard offer it as a checklist
    with no second list to keep in sync."""
    chap_dir = get_chapter_dir(project_name, chapter_num)
    entries = sorted(chap_dir.iterdir()) if chap_dir.exists() else []
    return entries + generated_dirs_for_chapter(project_name, chapter_num)
