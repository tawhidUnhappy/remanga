"""Project/chapter directory layout and metadata persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from remanga.json_io import read_json_or, write_json


def get_projects_dir() -> Path:
    p = Path("projects")
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_project_dir(project_name: str) -> Path:
    clean_proj = str(project_name).strip().replace("/", "_").replace("\\", "_")
    return get_projects_dir() / clean_proj


def get_chapter_dir(project_name: str, chapter_num: str) -> Path:
    clean_chap = str(chapter_num).strip().replace("/", "_").replace("\\", "_")
    return get_project_dir(project_name) / "chapters" / f"chapter_{clean_chap}"


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
    LLM is expected to read whichever of those it's handed."""
    meta = load_project_metadata(project_name)
    return {
        "project_name": project_name,
        "manga_name": meta.get("manga_title", ""),
        "manga_url": meta.get("manga_url", ""),
        "chapter": str(chapter_num),
    }


def save_project_metadata(project_name: str, data: Dict[str, Any]) -> None:
    meta_path = get_project_metadata_path(project_name)
    existing = load_project_metadata(project_name)
    existing.update(data)
    write_json(meta_path, existing)
    ensure_memory_file(project_name)


def list_projects() -> List[Dict[str, Any]]:
    root = get_projects_dir()
    results = []
    if not root.exists():
        return results

    for p in sorted(root.iterdir()):
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
