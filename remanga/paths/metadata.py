"""Project-level metadata files: project.json (manga identity/source),
memory.json (story continuity), youtube_format.json (the series' publishing
format lock) with its per-chapter youtube.json, manifest.json (small
per-chapter production bookkeeping), and the project listing the wizard's
picker reads."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from remanga.json_io import read_json_or, write_json

from .projects import get_chapter_dir, get_project_dir, get_projects_dir


def get_project_metadata_path(project_name: str) -> Path:
    return get_project_dir(project_name) / "project.json"


def get_memory_path(project_name: str) -> Path:
    return get_project_dir(project_name) / "memory.json"


def ensure_memory_file(project_name: str) -> Path:
    """Creates a blank placeholder memory.json at the project root the first time a project
    is touched, without ever clobbering continuity data an LLM has already written there."""
    memory_path = get_memory_path(project_name)
    if not memory_path.exists():
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text("", encoding="utf-8")
    return memory_path


def load_project_metadata(project_name: str) -> Dict[str, Any]:
    return read_json_or(get_project_metadata_path(project_name), {})


def chapter_identity_fields(project_name: str, chapter_num: str) -> Dict[str, Any]:
    """The project/manga/chapter identity fields every chapter_info.json starts
    from - shared by the primary vision archive (cropper/crop_report.py's
    write_chapter_info) and the size-capped LLM zip bundle (cropper/llm_zip.py),
    which adds its own part_index/total_parts per part on top of this same
    dict. See prompts/narration.md's "Chapter Identity" section for how the
    LLM is expected to read whichever of those it's handed. `reading_direction`
    ("right_to_left"/"left_to_right") comes from project.json's
    `reading_direction` field (see remanga/wizard/projects.py, which derives it from MangaDex's
    originalLanguage when a chapter has been downloaded), defaulting
    to "right_to_left" since that's the norm for native Japanese manga - the
    vast majority of what this pipeline imports."""
    meta = load_project_metadata(project_name)
    return {
        "project_name": project_name,
        "manga_name": meta.get("manga_title", ""),
        "manga_url": meta.get("manga_url", ""),
        "chapter": str(chapter_num),
        "reading_direction": meta.get("reading_direction", "right_to_left"),
    }


def save_project_metadata(project_name: str, data: Dict[str, Any]) -> None:
    meta_path = get_project_metadata_path(project_name)
    existing = load_project_metadata(project_name)
    existing.update(data)
    write_json(meta_path, existing)
    ensure_memory_file(project_name)


def get_youtube_path(project_name: str, chapter_num: str) -> Path:
    """{manga}/chapters/chapter_N/youtube.json - that chapter's YouTube title,
    description, tags and thumbnail brief, written by an LLM from the finished
    narration (see prompts/youtube_metadata.md). Lives in the chapter's SOURCE
    folder alongside narration.json rather than under a generated/ kind: like
    narration.json, nothing remanga has can regenerate it - it costs another
    LLM round-trip."""
    return get_chapter_dir(project_name, chapter_num) / "youtube.json"


def get_youtube_format_path(project_name: str) -> Path:
    """{manga}/youtube_format.json - the series' publishing format lock: title
    template, description skeleton, fixed blocks, core tags, hashtags and
    thumbnail style. One file for the whole manga, written on the first chapter
    and obeyed by every chapter after it, which is what makes chapter 12's video
    recognizable as the same series as chapter 3."""
    return get_project_dir(project_name) / "youtube_format.json"


def ensure_youtube_format_file(project_name: str) -> Path:
    """Creates a blank placeholder youtube_format.json at the project root the
    first time the YouTube step runs, without ever clobbering a format an LLM
    has already written there - same pattern as ensure_memory_file(). Blank,
    not `{}`: an empty file is what has_real_json_content() reads as "not
    written yet", and it's what the prompt's "you weren't given a format lock,
    so design one" branch keys off."""
    path = get_youtube_format_path(project_name)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return path


def get_pipeline_path(project_name: str) -> Path:
    """{manga}/pipeline.json - that project's ordered list of pipeline step
    names (see remanga.pipeline). Just a path lookup here, same as every
    other per-project metadata file in this module - the default-steps
    fallback and the "write it if missing" helper live in remanga.pipeline
    itself, since they need STEP_REGISTRY's default order, which this
    low-level paths package deliberately knows nothing about."""
    return get_project_dir(project_name) / "pipeline.json"


def get_manifest_path(project_name: str) -> Path:
    """{manga}/manifest.json - ONE file for the whole project carrying the
    informational bookkeeping that used to be three separate, never-read-back
    files repeated in every chapter folder (pages_metadata.json,
    panels_manifest.json, chapter_info.json). Keyed by chapter number, one
    section per production stage that wants to record something about a
    chapter (currently "pages" and "panels") - deliberately kept to small
    summary fields only (counts, ids, a timestamp), never a per-item dump.
    A per-panel/per-page listing (path, crop box, width/height, ...) is
    exactly the bloat those three files were replaced to get rid of - that
    detail already lives in full wherever it's actually needed (panels/
    itself, each package format's own per-part manifest), so repeating it
    here a second time just to sit unread would recreate the same problem
    under a new filename. If a future caller genuinely needs per-item data
    back, resist the urge to reach for this file - it means the caller
    should read the real source (panels/, pages/) instead."""
    return get_project_dir(project_name) / "manifest.json"


def read_manifest(project_name: str) -> Dict[str, Any]:
    return read_json_or(get_manifest_path(project_name), {"chapters": {}})


def update_manifest_chapter(project_name: str, chapter_num: str, section: str, data: Any) -> None:
    """Read-modify-write manifest.json['chapters'][chapter_num][section] = data.
    Chapters/sections are independent - downloader writes "pages" (called
    once per chapter, well before cropping touches this file), cropper
    writes "panels" (called once per chapter, after downloader already has)
    - so there's no cross-stage write race within a single chapter's
    production run, and each stage only ever rewrites its own section,
    never another chapter's or another stage's."""
    manifest = read_manifest(project_name)
    manifest.setdefault("chapters", {}).setdefault(str(chapter_num), {})[section] = data
    write_json(get_manifest_path(project_name), manifest)


def list_projects() -> List[Dict[str, Any]]:
    root = get_projects_dir()
    results = []
    if not root.exists():
        return results

    # Case-insensitive so e.g. "reincarnated..." (lowercase r) doesn't sort
    # after every capitalized project name - plain sorted() on Path objects
    # is ASCII/case-sensitive, which reads as a scrambled, seemingly
    # unstable order to anyone not thinking in ASCII code points.
    for p in sorted(root.iterdir(), key=lambda entry: entry.name.casefold()):
        if p.is_dir():
            meta = load_project_metadata(p.name)
            chapters_dir = p / "chapters"
            chapters = []
            if chapters_dir.exists():
                for c in sorted(chapters_dir.iterdir()):
                    if c.is_dir() and c.name.startswith("chapter_"):
                        ch_num = c.name.replace("chapter_", "")
                        chapters.append(ch_num)
            results.append({
                "name": p.name,
                "path": p,
                "manga_url": meta.get("manga_url", ""),
                "manga_id": meta.get("manga_id", ""),
                "last_chapter": meta.get("last_chapter", ""),
                "chapters": chapters,
            })
    return results
