"""Resolves a crops.json page entry (filename and/or index) to an actual
downloaded page image on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def locate_page_file(pages_dir: Path, filename: Optional[str], page_index: Optional[int]) -> Optional[Path]:
    """Resolves target page image path using filename or numeric index fallback."""
    if filename and (pages_dir / filename).exists():
        return pages_dir / filename

    if page_index is not None:
        candidates = (
            list(pages_dir.glob(f"page_{page_index:03d}.*")) +
            list(pages_dir.glob(f"page_{page_index:02d}.*")) +
            list(pages_dir.glob(f"page_{page_index}.*"))
        )
        if candidates:
            return candidates[0]

    all_pages = sorted(list(pages_dir.glob("page_*.*")))
    if page_index and 1 <= page_index <= len(all_pages):
        return all_pages[page_index - 1]

    return None
