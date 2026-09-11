"""Finding a project's chapters, and ordering them the way a reader would.

Imported by nearly everything that works across chapters (the CLI's chapter
selections, the wizard's pickers, verify, remix), so it deliberately depends
on nothing but paths - importing it can never drag in the audio/video
stack."""

from __future__ import annotations

import math
from collections.abc import Sequence

from remanga.paths import get_project_dir


def chapter_key(chapter_num: str) -> str:
    """The chapter numbers that mean the same chapter, as one key: "07", "7"
    and "7.0" collapse together. Used wherever two spellings of a chapter
    number have to be recognised as one - deduplicating MangaDex's feed,
    looking a chapter up in it, and checking a typed selection against it -
    so none of those can disagree about what counts as the same chapter."""
    text = str(chapter_num).strip()
    try:
        return f"{float(text):g}"
    except ValueError:
        return text.lstrip("0") or text


def chapter_sort_key(chapter_num: str):
    """Numeric sort where possible ("2" before "10"), falling back to plain
    string sort for anything that isn't a plain number (a bonus/special
    chapter label) - same tolerance remanga.cropper.naming.fmt_chapter has
    for non-numeric chapter labels, just for ordering instead of padding."""
    try:
        return (0, float(chapter_num))
    except ValueError:
        return (1, chapter_num)


def discover_chapters(project_name: str) -> list[str]:
    """Every chapter this project has a chapters/chapter_N/ directory for,
    in reading order. Doesn't filter by production status - callers decide
    what "ready" means for their own purpose."""
    chapters_root = get_project_dir(project_name) / "chapters"
    if not chapters_root.exists():
        return []
    nums = [
        d.name[len("chapter_"):]
        for d in chapters_root.iterdir()
        if d.is_dir() and d.name.startswith("chapter_")
    ]
    return sorted(nums, key=chapter_sort_key)


def _range_bounds(token: str) -> tuple[float, float] | None:
    """(low, high) for an 'N-M' token, high exclusive; None when the token
    isn't a numeric range (a plain number, or a label with a dash in it).

    A whole-number end covers every part of that chapter: '1-5' runs up to,
    but not including, 6 - so 5.1 and 5.2 are in it. A manga split into
    parts often has no chapter "5" at all, only 5.1 and 5.2, and a range
    that silently stopped at 4.2 would drop the very chapter it names. A
    decimal end is exact: '1-4.1' stops at 4.1. Either end may come first."""
    low_text, dash, high_text = token.partition("-")
    if not dash:
        return None
    try:
        ends = sorted([(float(low_text), low_text.strip()), (float(high_text), high_text.strip())])
    except ValueError:
        return None
    (low, _), (high, high_as_typed) = ends
    if high.is_integer() and "." not in high_as_typed:
        return low, high + 1
    return low, math.nextafter(high, math.inf)


def expand_chapter_selection(raw: str, available: Sequence[str], *, strict: bool = False) -> list[str]:
    """Comma-separated chapter numbers and/or ranges ('1,3,7-9') as the list
    of chapters they name, in reading order.

    Ranges expand only against `available` - the chapters the caller can
    actually act on (a project's folders for a wipe, MangaDex's listing for
    a download) - so '1-9999' can't manufacture chapters that don't exist,
    and every chapter numbered inside the range is included, 2.1 and 12.5
    as much as 3 (see _range_bounds for where a range ends).

    A plain number comes back spelled the way `available` spells it ("02"
    typed, "2" returned), so it names the same folder. One that isn't in
    `available` passes through as typed, unless `strict`, which raises
    ValueError naming every such chapter instead - for a download, where a
    chapter MangaDex doesn't list can't be fetched and should be refused
    before anything starts, not discovered halfway through."""
    spelled = {chapter_key(chapter): chapter for chapter in available}
    picked: dict[str, str] = {}
    unknown: list[str] = []
    for token in (t.strip() for t in raw.split(",")):
        if not token:
            continue
        bounds = _range_bounds(token)
        if bounds is None:
            key = chapter_key(token)
            if key not in spelled:
                unknown.append(token)
            picked.setdefault(key, spelled.get(key, token))
            continue
        low, high = bounds
        for chapter in available:
            try:
                value = float(chapter)
            except ValueError:
                continue
            if low <= value < high:
                picked.setdefault(chapter_key(chapter), chapter)
    if strict and unknown:
        raise ValueError(
            f"No chapter {', '.join(unknown)} in the list ({len(available)} chapter(s): "
            f"{available[0] if available else '-'} … {available[-1] if available else '-'})."
        )
    return sorted(picked.values(), key=chapter_sort_key)


