"""A chapter's page and panel files on disk, in reading order."""

from __future__ import annotations

from pathlib import Path

from remanga.paths import get_pages_dir, get_panels_dir

PAGE_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


PANEL_IMAGE_EXTS = PAGE_IMAGE_EXTS


def page_files(project: str, chapter: str) -> list[Path]:
    """The chapter's downloaded pages, in order."""
    pages_dir = get_pages_dir(project, chapter)
    if not pages_dir.exists():
        return []
    return sorted(p for p in pages_dir.iterdir() if p.is_file() and p.suffix.lower() in PAGE_IMAGE_EXTS)


def panel_files(project: str, chapter: str) -> list[Path]:
    """The panels cut from this chapter's pages, in reading order - their
    names sort into it (cropper/naming.py)."""
    panels_dir = get_panels_dir(project, chapter, create=False)
    if not panels_dir.exists():
        return []
    return sorted(p for p in panels_dir.iterdir() if p.is_file() and p.suffix.lower() in PANEL_IMAGE_EXTS)
