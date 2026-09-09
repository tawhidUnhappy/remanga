"""What's on disk for a chapter, and what a given reset would remove.

Pure listing - nothing here deletes anything. Every destructive path
(restart, wipe, and the whole-project wipe a regenerate-all runs first)
builds what it prints from these functions, so what the user is shown
before it happens is literally the list that gets passed to the delete
loop."""

from __future__ import annotations

from pathlib import Path

from remanga.paths import GENERATED_KINDS, get_chapter_dir, get_generated_dir, get_project_dir
from remanga.reset.modes import PROJECT_KEEP, keep_set


def generated_dirs_for_chapter(project_name: str, chapter_num: str) -> list[Path]:
    """Every {manga}/{kind}/chapter_N/ directory that currently exists for
    this chapter, across every GENERATED_KINDS - what every restart mode
    wipes in full, regardless of mode."""
    dirs = []
    for kind in GENERATED_KINDS:
        d = get_generated_dir(project_name, kind, chapter_num, create=False)
        if d.exists():
            dirs.append(d)
    return dirs


def project_wipe_candidates(project_name: str) -> list[Path]:
    """Everything a whole-project wipe would delete: every top-level entry
    under projects/{manga}/ whose name isn't in PROJECT_KEEP - audio/,
    video/, panels_zip/ and every other generated directory, in full,
    including the parts of them no per-chapter listing above ever reaches
    (the full-recap join's own _work/ and finished MP4, and any artifact
    directory belonging to a chapter that isn't in the current run).

    Empty for a project that doesn't exist on disk yet, rather than an
    error: "nothing generated to delete" is the right answer for it, and
    the caller reports that the same way it reports an already-clean
    project."""
    project_dir = get_project_dir(project_name)
    if not project_dir.exists():
        return []
    return [entry for entry in sorted(project_dir.iterdir()) if entry.name not in PROJECT_KEEP]


# Generated kinds that are DERIVED from other generated kinds rather than
# from the source tree - cheap to rebuild, and the only things a
# "re-render, keep the narration" reset needs to remove. audio/ is
# deliberately absent: it holds the raw synthesized speech, which is the
# expensive artifact this whole split exists to protect (see
# paths.get_modified_audio_dir).
DERIVED_KINDS = ("audio_modified", "video")


def derived_wipe_candidates(project_name: str) -> list[Path]:
    """Every derived-audio and video directory in the project, plus the
    full-recap join's own output - what a "keep the narration, redo
    everything made from it" reset deletes.

    The full-recap directory is included for the same reason wipe_project
    does not delegate to wipe_chapter: the joined master and its _work/ are
    filed under no chapter, so a per-chapter sweep would leave a stale
    full-manga video sitting next to freshly rebuilt chapters."""
    project_dir = get_project_dir(project_name)
    if not project_dir.exists():
        return []
    out: list[Path] = []
    for kind in DERIVED_KINDS:
        kind_dir = project_dir / kind
        if kind_dir.exists():
            out.extend(sorted(kind_dir.iterdir()))
    return out


def restart_candidates(project_name: str, chapter_num: str, *, mode: str = "hard") -> list[Path]:
    """Everything a restart of this `mode` would delete (before the
    narration.json re-emptying a marks_only restart also does - see
    restart_chapter): the not-kept part of the chapter's source folder, plus
    every generated directory this chapter has anything in."""
    chap_dir = get_chapter_dir(project_name, chapter_num)
    keep = keep_set(mode)
    source = [entry for entry in sorted(chap_dir.iterdir()) if entry.name not in keep] if chap_dir.exists() else []
    return source + generated_dirs_for_chapter(project_name, chapter_num)


def wipeable_entries(project_name: str, chapter_num: str) -> list[Path]:
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
