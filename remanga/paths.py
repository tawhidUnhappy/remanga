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


def load_project_metadata(project_name: str) -> Dict[str, Any]:
    return read_json_or(get_project_metadata_path(project_name), {})


def save_project_metadata(project_name: str, data: Dict[str, Any]) -> None:
    meta_path = get_project_metadata_path(project_name)
    existing = load_project_metadata(project_name)
    existing.update(data)
    write_json(meta_path, existing)


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
