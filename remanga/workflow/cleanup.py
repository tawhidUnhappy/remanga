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
