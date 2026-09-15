"""A chapter's page files: which file each MangaDex page is saved as, how a
page is checked against the SHA-256 MangaDex names it after, and the pages
zip built from them."""

from __future__ import annotations

import hashlib
import re
import shutil
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from remanga.console import console, escape as _esc
from remanga.paths import get_pages_zip_path

# MangaDex@Home names every page file after the SHA-256 of its own bytes
# ("3-<64 hex digits>.png") - checked against real chapters at both image
# qualities. That's what makes re-verifying a downloaded chapter a check of
# each page's content rather than of its size.
PAGE_CHECKSUM = re.compile(r"-([0-9a-f]{64})\.\w+$")

# config's image_quality -> (the at-home response's key for its file list,
# the URL path segment the files are served under). The smaller images are
# spelled differently in the two places, and config.py documents
# "data-saver", so both spellings are accepted.
IMAGE_QUALITY = {
    "data": ("data", "data"),
    "data-saver": ("dataSaver", "data-saver"),
    "dataSaver": ("dataSaver", "data-saver"),
}


@dataclass(frozen=True)
class PageFile:
    """One page of a chapter: where it's saved, and MangaDex's filename for it."""

    path: Path
    source: str

    @property
    def checksum(self) -> str | None:
        match = PAGE_CHECKSUM.search(self.source)
        return match.group(1) if match else None

    def matches(self, content: bytes, trust_unchecked: bool = True) -> bool:
        """Whether `content` is this page: non-empty, and equal to MangaDex's
        checksum when it gave one (else `trust_unchecked` decides)."""
        if not content:
            return False
        if self.checksum is None:
            return trust_unchecked
        return hashlib.sha256(content).hexdigest() == self.checksum

    def valid_on_disk(self, trust_unchecked: bool) -> bool:
        return self.path.is_file() and self.matches(self.path.read_bytes(), trust_unchecked)


def remove_paths(paths: Iterable[Path]) -> None:
    """Deletes files, links and folders alike."""
    for path in list(paths):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def create_pages_zip(project_name: str, chapter_num: str, pages_dir: Path) -> Path:
    """Package downloaded pages into a single ZIP archive for easy LLM uploading."""
    zip_path = get_pages_zip_path(project_name, chapter_num)
    if zip_path.exists():
        zip_path.unlink()

    pages = sorted(p for p in pages_dir.iterdir() if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in pages:
            zf.write(p, arcname=p.name)

    console.print(f"[bold green]✓ Created Pages ZIP archive:[/] {_esc(str(zip_path))}")
    return zip_path
