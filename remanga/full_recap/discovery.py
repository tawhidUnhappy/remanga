"""Finding a project's chapters, and ordering them the way a reader would.

Imported by nearly everything that works across chapters (the CLI's chapter
selections, the wizard's pickers, verify, remix), so it deliberately depends
on nothing but paths - importing it can never drag in the audio/video
stack."""

from __future__ import annotations

from typing import List

from remanga.paths import get_project_dir


def chapter_sort_key(chapter_num: str):
    """Numeric sort where possible ("2" before "10"), falling back to plain
    string sort for anything that isn't a plain number (a bonus/special
    chapter label) - same tolerance remanga.cropper.naming.fmt_chapter has
    for non-numeric chapter labels, just for ordering instead of padding."""
    try:
        return (0, float(chapter_num))
    except ValueError:
        return (1, chapter_num)


def discover_chapters(project_name: str) -> List[str]:
    """Every chapter this project has a chapters/chapter_N/ directory for,
    in reading order. Doesn't filter by production status - callers decide
    what "ready" means for their own purpose."""
    chapters_root = get_project_dir(project_name) / "chapters"
    if not chapters_root.exists():
        return []
    nums = []
    for d in chapters_root.iterdir():
        if d.is_dir() and d.name.startswith("chapter_"):
            nums.append(d.name[len("chapter_"):])
    return sorted(nums, key=chapter_sort_key)


