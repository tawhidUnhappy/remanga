"""Chapter reset: wipe generated production artifacts while preserving the
chapter's source folder (or the parts of it each mode keeps).

Since paths.get_chapter_dir now holds ONLY source material - pages/,
panels/, crops.json, narration.json (see that function's docstring) - and
everything derived lives one level up under paths.get_generated_dir's
per-kind, per-chapter directories (sheets, sheets_zip, sheets_folders,
panels_zip, panels_pdf, pages_zip, audio, video), every restart mode wipes
ALL of those generated directories for this chapter, every time - there's
never a reason to leave a stale sheet, zip, audio clip, or rendered frame
sitting in {manga}/ once the source it came from might change. The three
modes below only differ in how much of the SOURCE folder they keep."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from remanga.console import console
from remanga.json_io import write_json
from remanga.paths import GENERATED_KINDS, get_chapter_dir, get_generated_dir, get_manifest_path, read_manifest

# Chapter-source entries kept by each restart mode - see module docstring.
# "pages" (the downloaded scans) is always kept by every mode; a restart
# never re-downloads unless reverify_downloads finds something missing.
KEEP_ON_RESTART = {"pages"}
KEEP_ON_MARKS_ONLY_RESTART = KEEP_ON_RESTART | {"crops.json"}
KEEP_ON_SOFT_RESTART = KEEP_ON_RESTART | {"crops.json", "panels", "narration.json", "narration_review.json", "narration_reviews"}

RESTART_MODES = ("hard", "marks_only", "soft")


def _keep_set(mode: str) -> set:
    if mode == "hard":
        base = KEEP_ON_RESTART
    elif mode == "marks_only":
        base = KEEP_ON_MARKS_ONLY_RESTART
    elif mode == "soft":
        base = KEEP_ON_SOFT_RESTART
    else:
        raise ValueError(f"Unknown restart mode {mode!r} - expected one of {RESTART_MODES}")

    # pages.zip lives under {manga}/pages_zip/chapter_N/ now (a generated
    # artifact, not part of the source folder), so it's handled by the
    # generated-dirs wipe below, not this keep set - nothing to add here
    # anymore.
    return base


def _generated_dirs_for_chapter(project_name: str, chapter_num: str) -> List[Path]:
    """Every {manga}/{kind}/chapter_N/ directory that currently exists for
    this chapter, across every GENERATED_KINDS - what every restart mode
    wipes in full, regardless of mode (see module docstring)."""
    dirs = []
    for kind in GENERATED_KINDS:
        d = get_generated_dir(project_name, kind, chapter_num, create=False)
        if d.exists():
            dirs.append(d)
    return dirs


def restart_candidates(project_name: str, chapter_num: str, *, mode: str = "hard") -> List[Path]:
    """Lists everything a restart of this `mode` would delete (before any
    narration.json re-emptying a marks_only restart also does - see
    restart_chapter): the not-kept part of the chapter's source folder, plus
    every generated directory this chapter has anything in. Doesn't delete
    anything."""
    chap_dir = get_chapter_dir(project_name, chapter_num)
    keep = _keep_set(mode)
    source_candidates = [entry for entry in sorted(chap_dir.iterdir()) if entry.name not in keep] if chap_dir.exists() else []
    return source_candidates + _generated_dirs_for_chapter(project_name, chapter_num)


def restart_chapter(
    project_name: str,
    chapter_num: str,
    *,
    mode: str = "hard",
    reverify_downloads: bool = True,
) -> List[Path]:
    """
    Deletes generated chapter artifacts while preserving the source folder
    (or the part of it each mode keeps) - so the chapter can be reprocessed
    without redoing more than necessary. Every mode wipes every generated
    {manga}/{kind}/chapter_N/ directory for this chapter in full (sheets,
    zips/PDFs, audio, video, the final MP4) - see module docstring for why
    that's always safe: everything in them is cheaply rebuilt from whatever
    of the source folder the chosen mode keeps. Three levels, from most to
    least destructive about the SOURCE folder itself:

    - "hard" (default, the original restart behavior): wipes crops.json and
      panels/ too - keeps only pages/.
    - "marks_only": also keeps crops.json, but still wipes narration.json -
      then recreates it as an empty placeholder (the same blank-file state
      it's in before any LLM has ever touched it - see
      json_io.has_real_json_content), so it reads as "not yet generated"
      rather than just missing.
    - "soft": also keeps panels/ and narration.json (see
      KEEP_ON_SOFT_RESTART) - the source folder is untouched entirely, only
      the generated directories get wiped.

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

    # panels/ no longer exists (hard/marks_only) or is being treated as
    # about to be re-cropped either way - this chapter's "panels" bookkeeping
    # in the shared manifest.json is stale regardless of mode, so it's
    # cleared here rather than left describing panel files that are gone.
    manifest = read_manifest(project_name)
    chapter_entry = manifest.get("chapters", {}).get(str(chapter_num))
    if chapter_entry and "panels" in chapter_entry:
        del chapter_entry["panels"]
        write_json(get_manifest_path(project_name), manifest)

    if reverify_downloads:
        _reverify_downloads(project_name, chapter_num)

    return candidates


def wipeable_entries(project_name: str, chapter_num: str) -> List[Path]:
    """Every deletable item for this chapter right now: the chapter's own
    source-folder entries (pages/, crops.json, panels/, narration.json,
    ...) plus every generated {kind}/chapter_N/ directory that currently
    exists (sheets, sheets_zip, panels_zip, audio, video, ...). This is the
    live menu `wipe_chapter` below picks its "keep" list from - unlike
    restart_chapter's three fixed modes above (each keeping one hardcoded
    set), nothing here is wired in; it's simply "what's actually here right
    now for this chapter", so a wizard can offer it as-is with no separate
    list to keep in sync."""
    chap_dir = get_chapter_dir(project_name, chapter_num)
    entries = sorted(chap_dir.iterdir()) if chap_dir.exists() else []
    return entries + _generated_dirs_for_chapter(project_name, chapter_num)


def wipe_chapter(
    project_name: str, chapter_num: str, keep_names: set, *, reverify_downloads: bool = True,
) -> List[Path]:
    """Deletes every entry from wipeable_entries() whose name isn't in
    `keep_names` - the fully dynamic counterpart to restart_chapter's three
    fixed modes, letting a caller keep any combination at all (e.g. keep
    video/ and narration.json but wipe panels/ to re-crop with new
    settings, something none of the "hard"/"marks_only"/"soft" modes above
    can express). `reverify_downloads` behaves exactly like
    restart_chapter's own flag - re-checks/re-fetches pages/ afterward
    regardless of whether pages/ itself was kept or wiped, so a wipe that
    deleted pages/ ends up with it re-downloaded rather than just missing.
    Returns the paths that were removed."""
    candidates = [e for e in wipeable_entries(project_name, chapter_num) if e.name not in keep_names]
    for entry in candidates:
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    if "panels" not in keep_names:
        manifest = read_manifest(project_name)
        chapter_entry = manifest.get("chapters", {}).get(str(chapter_num))
        if chapter_entry and "panels" in chapter_entry:
            del chapter_entry["panels"]
            write_json(get_manifest_path(project_name), manifest)

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
