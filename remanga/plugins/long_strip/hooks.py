"""The "long_strip" layout's hooks (see plugins/_kinds.py:Layout)."""

from __future__ import annotations

from pathlib import Path

from remanga.plugins.long_strip.build import ensure_strip, strip_dir, strip_panels
from remanga.plugins.long_strip.layout import looks_like_strip, source_pages


def matches(project: str, chapter: str) -> bool:
    return looks_like_strip(source_pages(project, chapter))


def mark(project: str, chapters: list[str], config) -> list[str]:
    """A tab per chapter, one after another - the whole chapter as one strip."""
    from remanga.plugins.long_strip.web.server import launch_and_wait_strip

    for chapter in chapters:
        launch_and_wait_strip(project, chapter, config.marker)
    return list(chapters)


def pages_dir(project: str, chapter: str, build: bool = True) -> Path:
    """strip/: the downloaded images re-cut between panels - brought up to
    date first unless `build` is False (for callers that only list names)."""
    if build:
        ensure_strip(project, chapter)
    return strip_dir(project, chapter)


def detect(pages_dir: Path, page_paths: list[Path], marker_config, on_page_done) -> dict[str, list]:
    """The panels were already found when the strip was cut."""
    found = strip_panels(pages_dir)
    results = {path.name: found.get(path.name, []) for path in page_paths}
    for filename, boxes in results.items():
        on_page_done(filename, boxes)
    return results


def prepare_cut(project: str, chapter: str) -> None:
    """The strip and crops.json follow the Strip Marker's marks."""
    ensure_strip(project, chapter)
