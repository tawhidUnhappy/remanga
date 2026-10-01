"""The "pages" layout's hooks (see plugins/_kinds.py:Layout)."""

from __future__ import annotations

from pathlib import Path

from remanga.paths import get_pages_dir


def matches(project: str, chapter: str) -> bool:
    return True


def mark(project: str, chapters: list[str], config) -> list[str]:
    """One Panel Marker tab for all of them."""
    from remanga.webui import launch_and_wait_all

    return launch_and_wait_all(project, chapters, config.marker)


def pages_dir(project: str, chapter: str, build: bool = True) -> Path:
    return get_pages_dir(project, chapter)


def detect(pages_dir: Path, page_paths: list[Path], marker_config, on_page_done) -> dict[str, list]:
    from remanga.plugins.magi.assist import detect_panels_for_pages

    return detect_panels_for_pages(page_paths, marker_config, on_page_done=on_page_done)
