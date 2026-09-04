"""What this chapter currently has that can be handed to an LLM.

The narration step doesn't pick a format for you - it lists what's actually
been built, in order of preference, and you upload any one group. This is
the discovery half of that (which formats exist on disk right now), kept
apart from the printing half so the "nothing was built at all" case can be
detected and explained rather than printed as an empty list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from remanga.config import RemangaConfig
from remanga.paths import (
    get_chapter_dir, get_panels_pdf_dir, get_panels_zip_dir, get_sheets_dir, get_sheets_zip_dir,
)


@dataclass(frozen=True)
class UploadGroup:
    """One complete, self-sufficient upload option. `parts` is every file
    that group consists of - more than one means it was split to stay under
    a size cap, and all of its parts go up together."""

    kind: str
    parts: List[Path]

    @property
    def is_split(self) -> bool:
        return len(self.parts) > 1


def _files_in(directory: Path, pattern: str) -> List[Path]:
    return sorted(directory.glob(pattern)) if directory.exists() else []


def upload_groups(project: str, chapter: str, config: RemangaConfig) -> List[UploadGroup]:
    """Every upload option that exists for this chapter, best first.

    Packaged bundles come first, in the order they were configured to be
    built. If no zip/PDF format is active at all - a deliberate, valid
    setup for an LLM whose upload interface won't take an archive - this
    falls back to whatever raw images are on disk: the sheets/ directory
    first (denser, fewer files, cheaper on vision tokens), then the
    always-generated panels/ directory."""
    package = config.cropper.package
    groups: List[UploadGroup] = []

    if package.pdf_active:
        pdf_dir = get_panels_pdf_dir(project, chapter, create=False)
        parts = _files_in(pdf_dir, "panels_*.pdf") + _files_in(pdf_dir, "panels_*.zip")
        if parts:
            groups.append(UploadGroup("PDF bundle", parts))

    if package.panels_zip_active:
        parts = _files_in(get_panels_zip_dir(project, chapter, create=False), "panels_*.zip")
        if parts:
            groups.append(UploadGroup("zip bundle", parts))

    if package.sheets_zip_active:
        parts = _files_in(get_sheets_zip_dir(project, chapter, create=False), "sheets_*.zip")
        if parts:
            groups.append(UploadGroup("sheets zip bundle", parts))

    if groups:
        return groups

    if package.sheets:
        parts = [p for p in _files_in(get_sheets_dir(project, chapter, create=False), "*") if p.is_file()]
        if parts:
            return [UploadGroup("sheets (unzipped)", parts)]

    parts = [p for p in _files_in(get_chapter_dir(project, chapter) / "panels", "*") if p.is_file()]
    if parts:
        return [UploadGroup("panels (unzipped)", parts)]

    return []
