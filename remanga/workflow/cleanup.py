"""Resetting or deleting a chapter - the one place that removes a user's files,
and the guard that keeps it inside the project it was given."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from remanga.paths import (
    GENERATED_KINDS,
    get_chapter_dir,
    get_crops_path,
    get_generated_dir,
    get_narration_path,
    get_panels_dir,
    get_project_dir,
)
from remanga.paths.review import get_narration_review_path

# What making a video produces, and nothing else. The PDF is deliberately
# not in here: it is slow to make, it is what the user hands to the LLM, and
# nothing about narrating or rendering can invalidate it. Neither is anything
# under chapters/ - the pages, the cut panels, crops.json and the pasted
# narration are what a run is made FROM, and losing the narration would mean
# going back to the LLM.
REMADE_KINDS = ("audio", "audio_modified", "subtitles", "video")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return path.resolve() != root.resolve()
    except ValueError:
        return False


def _chapter_paths(project: str, chapter: str, *, with_pages: bool) -> list[Path]:
    """What resetting (or, `with_pages`, deleting) a chapter aims at - each
    one checked to be a chapter folder or file strictly inside this project,
    so a blank or odd project/chapter name can never widen it.

    Everything it aims at, including what isn't there. The caller deletes the
    ones that exist, and prunes from all of them: a second reset of a chapter
    whose pdf/chapter_3 went in the first one must still be able to take the
    empty pdf/ the first one left behind."""
    if not str(project).strip() or not str(chapter).strip():
        raise ValueError("A project and a chapter are needed.")
    project_dir = get_project_dir(project)
    chapter_dir = get_chapter_dir(project, chapter)
    paths = [get_generated_dir(project, kind, chapter, create=False) for kind in GENERATED_KINDS]
    if with_pages:
        paths.append(chapter_dir)
    else:
        # The panels are cut again from crops.json in seconds; the marks and
        # the pasted narration are the two things nothing can rebuild, and
        # only the narration is a reset's business.
        paths += [get_narration_path(project, chapter), get_panels_dir(project, chapter, create=False)]
    for path in paths:
        if not _inside(path, project_dir) or not path.name.startswith(("chapter_", "narration.json", "panels")):
            raise ValueError(f"Refusing to delete {path} - it isn't one chapter's file inside {project_dir}.")
    return paths


def _prune_empty_dirs(paths: list[Path], project_dir: Path) -> list[Path]:
    """Removes the folders a deletion has left empty, walking up from each
    path it aimed at and stopping below the project's own folder.

    A reset takes a chapter out of pdf/, audio/, audio_modified/, subtitles/
    and video/, and on the last (often the only) chapter that leaves five
    empty folders standing in the project - a layout that says work was done
    here when none of it is left. The chapter folder itself is the same story
    after a delete: chapters/ stays behind, empty.

    Only ever a folder this call emptied, and only inside the project (_inside
    excludes the project folder itself, so project.json and a project with no
    chapters left are never at risk). A folder someone else is writing into
    while this runs simply isn't empty, and rmdir refusing it is the right
    answer, so an OSError ends that walk instead of failing the reset that has
    already happened."""
    pruned: list[Path] = []
    for path in paths:
        parent = path.parent
        while _inside(parent, project_dir) and parent.is_dir():
            try:
                parent.rmdir()   # refuses a folder that isn't empty - the check and the removal in one step
            except OSError:
                break
            pruned.append(parent)
            parent = parent.parent
    return pruned


def drop_mix_and_video(project: str, chapter: str) -> list[Path]:
    """Deletes a chapter's mixed master and rendered video, keeping the raw
    synthesized clips (audio/) and audio_timing.json - what Remake audio
    leaves behind after narrating, mixing and rendering once to prove the
    narration is good, so the mix and the render can be redone later (Make
    video, unforced) from the clips already on disk rather than kept twice
    over."""
    project_dir = get_project_dir(project)
    paths = [get_generated_dir(project, kind, chapter, create=False) for kind in ("audio_modified", "video")]
    for path in paths:
        if not _inside(path, project_dir) or not path.name.startswith("chapter_"):
            raise ValueError(f"Refusing to delete {path} - it isn't one chapter's file inside {project_dir}.")
    removed = [path for path in paths if path.exists()]
    import shutil
    for path in removed:
        shutil.rmtree(path)
    return removed


def drop_audio_and_video(project: str, chapter: str) -> list[Path]:
    """Deletes everything a video run makes - the narration clips, the mix,
    the word timings and the rendered video - so the run that follows starts
    from nothing (user request, 2026-09-21).

    Both Make video and Remake video do this, which is what makes a run mean
    the same thing every time: what is on disk afterwards is what THIS run
    produced, not a layer over whatever an earlier one left. It costs the
    reuse - a chapter is narrated again whether or not anything changed - and
    that was the choice, made knowing narration is the slow part.

    It is also what clears a folder that has been through a change of
    approach: switching from a clip per panel to batched takes leaves the old
    clips behind, and they are neither used nor obviously stale.

    The PDF is never touched (see REMADE_KINDS), and neither is anything the
    run is made from."""
    project_dir = get_project_dir(project)
    paths = [get_generated_dir(project, kind, chapter, create=False) for kind in REMADE_KINDS]
    for path in paths:
        if not _inside(path, project_dir) or not path.name.startswith("chapter_"):
            raise ValueError(f"Refusing to delete {path} - it isn't one chapter's file inside {project_dir}.")
    import shutil

    removed = [path for path in paths if path.exists()]
    for path in removed:
        shutil.rmtree(path)
    return removed


def drop_derived(project: str, chapter: str) -> list[Path]:
    """Deletes everything a chapter's sources produce - the cut panels, the
    PDF, the narration audio, the mix, the subtitles and the video - keeping
    only what nothing can rebuild: the pages, the panel marks (crops.json)
    and the pasted narration.json. The start of Remake from source."""
    import shutil

    project_dir = get_project_dir(project)
    paths = [get_generated_dir(project, kind, chapter, create=False) for kind in GENERATED_KINDS]
    paths.append(get_panels_dir(project, chapter, create=False))
    for path in paths:
        if not _inside(path, project_dir) or not path.name.startswith(("chapter_", "panels")):
            raise ValueError(f"Refusing to delete {path} - it isn't one chapter's file inside {project_dir}.")
    removed = [path for path in paths if path.exists()]
    for path in removed:
        shutil.rmtree(path)
    return removed + _prune_empty_dirs(paths, project_dir)


def reset_chapter(project: str, chapter: str, *, delete_pages: bool = False) -> list[Path]:
    """Deletes a chapter's PDF, cut panels, pasted narration, audio and video
    - and, with `delete_pages`, its downloaded pages and marks too, removing
    the chapter. Returns what was removed, the folders left empty by it
    included (user request, 2026-09-22): a reset that leaves pdf/, audio/,
    audio_modified/, subtitles/ and video/ standing there empty hasn't really
    put the project back as it was.

    Nothing has to recreate them: every folder here is made on demand the
    next time something is written to it (remanga/paths/projects.py)."""
    import shutil

    targets = _chapter_paths(project, chapter, with_pages=delete_pages)
    removed = [path for path in targets if path.exists()]
    for path in removed:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return removed + _prune_empty_dirs(targets, get_project_dir(project))


# --- Deleting chosen things (the chapter menu's "Delete chosen...") -------

@dataclass(frozen=True)
class Deletable:
    """One kind of thing a chapter has that can be deleted on its own."""
    key: str
    label: str
    hint: str


# In the order the pipeline makes them, so the list reads like the work.
DELETABLES = (
    Deletable("pages", "Downloaded pages", "pages/ - download again to get back"),
    Deletable("strip", "Long-strip pages", "strip/ - re-cut from the download"),
    Deletable("marks", "Panel marks", "crops.json (+ strip_marks.json) - your marking"),
    Deletable("panels", "Cut panels", "panels/ - cut again from the marks"),
    Deletable("pdf", "PDF", "pdf/ - Make PDF makes it again"),
    Deletable("narration", "Narration", "narration.json - the LLM's reply"),
    Deletable("review", "Narration review", "narration_review.json + past rounds"),
    Deletable("audio", "Narration audio", "audio/ - voice clips, slow to make"),
    Deletable("mix", "Mixed sound", "audio_modified/ - narration + music"),
    Deletable("subtitles", "Word timings", "subtitles/"),
    Deletable("video", "Video", "video/ - the finished MP4"),
)
_GENERATED = {"pdf": "pdf", "audio": "audio", "mix": "audio_modified", "subtitles": "subtitles", "video": "video"}


def _deletable_paths(project: str, chapter: str, key: str) -> list[Path]:
    """Where one Deletable lives for one chapter - each path checked to be
    that chapter's own, strictly inside the project."""
    if not str(project).strip() or not str(chapter).strip():
        raise ValueError("A project and a chapter are needed.")
    chapter_dir = get_chapter_dir(project, chapter)
    if key in _GENERATED:
        paths = [get_generated_dir(project, _GENERATED[key], chapter, create=False)]
    else:
        paths = {
            "pages": [chapter_dir / "pages"],
            "strip": [chapter_dir / "strip", chapter_dir / "strip.json"],
            "marks": [get_crops_path(project, chapter), chapter_dir / "strip_marks.json"],
            "panels": [get_panels_dir(project, chapter, create=False)],
            "narration": [get_narration_path(project, chapter)],
            "review": [get_narration_review_path(project, chapter), chapter_dir / "narration_reviews"],
        }[key]
    project_dir = get_project_dir(project)
    for path in paths:
        inside_chapter = _inside(path, chapter_dir)
        generated = path.name.startswith("chapter_") and _inside(path, project_dir)
        if not (inside_chapter or generated):
            raise ValueError(f"Refusing to delete {path} - it isn't one chapter's file inside {project_dir}.")
    return paths


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


def deletable_items(project: str, chapters: list[str]) -> list[tuple[Deletable, int, int]]:
    """What these chapters have on disk that can be deleted: (item, total
    bytes, how many of the chapters have it), leaving out what none has."""
    found = []
    for item in DELETABLES:
        having = []
        for chapter in chapters:
            present = [p for p in _deletable_paths(project, chapter, item.key) if p.exists()]
            if present:
                having.append(sum(_size(p) for p in present))
        if having:
            found.append((item, sum(having), len(having)))
    return found


def delete_items(project: str, chapter: str, keys: list[str]) -> list[Path]:
    """Deletes the chosen Deletables of one chapter; returns what was removed,
    the folders that left empty included (as reset_chapter does)."""
    import shutil

    targets = [path for key in keys for path in _deletable_paths(project, chapter, key)]
    removed = [path for path in targets if path.exists()]
    for path in removed:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return removed + _prune_empty_dirs(targets, get_project_dir(project))
