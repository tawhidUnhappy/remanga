"""Whether a chapter is a long strip (a webtoon, read by scrolling down) or
pages.

project.json's `layout` decides when it says anything: it is set from
MangaDex's "Long Strip" format tag when the project is made, and can be
written by hand ("long_strip" or "pages") for a manga MangaDex tags wrong.
Without it the chapter's own images decide - a long strip's are several
times taller than they are wide, a page never is - so a project made before
this existed needs nothing done to it."""

from __future__ import annotations

from pathlib import Path
from statistics import median

from PIL import Image

from remanga.paths import get_pages_dir, load_project_metadata

LONG_STRIP = "long_strip"
PAGES = "pages"
# MangaDex's "Long Strip" format tag.
LONG_STRIP_TAG = "3e2b8dae-350e-4ab8-a8ce-016e844b9f0d"
# Median height / width of a chapter's images from which it is a strip. A
# manga page is ~1.4, a double spread 0.7; webtoon uploads run 5-14.
STRIP_ASPECT = 2.5
PAGE_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def source_pages(project: str, chapter: str) -> list[Path]:
    """The chapter's downloaded images, in reading order."""
    pages_dir = get_pages_dir(project, chapter)
    if not pages_dir.is_dir():
        return []
    return sorted(p for p in pages_dir.iterdir() if p.is_file() and p.suffix.lower() in PAGE_IMAGE_EXTS)


def looks_like_strip(paths: list[Path]) -> bool:
    """Whether these images are strip slices, from their shape alone (image
    headers only - nothing is decoded)."""
    aspects = []
    for path in paths:
        with Image.open(path) as img:
            aspects.append(img.height / max(1, img.width))
    return bool(aspects) and median(aspects) >= STRIP_ASPECT


def is_long_strip(project: str, chapter: str) -> bool:
    layout = load_project_metadata(project).get("layout")
    if layout in (LONG_STRIP, PAGES):
        return layout == LONG_STRIP
    return looks_like_strip(source_pages(project, chapter))
