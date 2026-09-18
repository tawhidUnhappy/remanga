"""What more than one screen needs: where a path is shown from, the log
project-wide work writes to, and the chapter list as the table reads it."""

from __future__ import annotations

from pathlib import Path

from remanga import activity, workflow
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.paths import get_log_path


def _short(path: Path | str) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _global_log() -> Path:
    path = Path("projects") / "remanga.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


_STATUS = {"downloaded": ("✓ downloaded", "green"), "partial": ("◐ partial", "yellow"),
           "missing": ("+ new", "cyan"), "local": ("• local only", "dim")}


def _merge_rows(project: str, listing: list[dict]) -> list[dict]:
    from remanga.chapters import chapter_key, chapter_sort_key

    rows = [dict(entry) for entry in listing]
    listed = {chapter_key(entry["chapter"]) for entry in rows}
    rows += [{"chapter": ch, "status": "local", "title": "", "pages": None}
             for ch in workflow.local_chapters(project) if chapter_key(ch) not in listed]
    for row in rows:
        if row["status"] == "missing" and workflow.page_files(project, row["chapter"]):
            row["status"] = "partial"
    return sorted(rows, key=lambda row: chapter_sort_key(row["chapter"]))


def _fetch_listing(project: str, machine: RemangaConfig, refresh: bool) -> tuple[list[dict], bool]:
    """MangaDex's chapter list, with what it printed kept in the project log."""
    old = console.file
    activity.set_reporter(activity.Reporter())  # no progress bar drawn anywhere
    try:
        console.file = get_log_path(project).open("a", encoding="utf-8")
        return workflow.mangadex_chapters(project, machine.for_project(project), refresh=refresh), False
    except Exception:
        return [], True
    finally:
        activity.set_reporter(None)
        if console.file is not old:
            console.file.close()
        console.file = old
