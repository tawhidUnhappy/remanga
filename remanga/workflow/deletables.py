"""The chapter menu's "Delete chosen...": every kind of thing a chapter has on
disk that can go on its own, what of it these chapters have, and deleting
exactly what was ticked - each path checked to be that chapter's own inside
the project (cleanup.py's guard), and folders it empties removed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from remanga.paths import (
    get_chapter_dir,
    get_crops_path,
    get_generated_dir,
    get_narration_path,
    get_panels_dir,
    get_project_dir,
)
from remanga.paths.review import get_narration_review_path
from remanga.workflow.cleanup import inside, prune_empty_dirs


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
        inside_chapter = inside(path, chapter_dir)
        generated = path.name.startswith("chapter_") and inside(path, project_dir)
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
    return removed + prune_empty_dirs(targets, get_project_dir(project))
