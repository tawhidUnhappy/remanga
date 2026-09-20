"""Resetting or deleting a chapter - the one place that removes a user's files,
and the guard that keeps it inside the project it was given."""

from __future__ import annotations

from pathlib import Path

from remanga.paths import (
    GENERATED_KINDS,
    get_chapter_dir,
    get_generated_dir,
    get_narration_path,
    get_panels_dir,
    get_project_dir,
)

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
    """What resetting (or, `with_pages`, deleting) a chapter removes - each
    one checked to be a chapter folder or file strictly inside this project,
    so a blank or odd project/chapter name can never widen it."""
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
    return [path for path in paths if path.exists()]


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


def reset_chapter(project: str, chapter: str, *, delete_pages: bool = False) -> list[Path]:
    """Deletes a chapter's PDF, cut panels, pasted narration, audio and video
    - and, with `delete_pages`, its downloaded pages and marks too, removing
    the chapter. Returns what was removed."""
    import shutil

    removed = _chapter_paths(project, chapter, with_pages=delete_pages)
    for path in removed:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return removed
