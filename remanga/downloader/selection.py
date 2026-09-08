"""Turning what a user typed about chapters to *download* into an actual
chapter-number list - the download-side counterpart to
remanga.commands.selection.parse_chapter_selection, which expands ranges
against chapters a project already has on disk. Downloading needs the
opposite universe: a range like '1-24' has to expand against what MangaDex
actually lists upstream, not what's already been fetched, or it could never
reach a chapter this project doesn't have yet."""

from __future__ import annotations

from collections.abc import Sequence

from remanga.full_recap.discovery import chapter_sort_key


def parse_remote_chapter_selection(raw: str, available_chapters: Sequence[str]) -> list[str]:
    """Comma-separated chapter numbers and/or numeric ranges ('N-M'),
    expanded only against `available_chapters` (MangaDex's own listing for
    this manga) - so '1-9999' can't manufacture chapter numbers MangaDex
    never published, and a range still resolves correctly against
    non-integer chapter labels (12.5, decimals) the way plain float
    comparison allows."""
    result: set = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo_s, _, hi_s = token.partition("-")
            try:
                lo, hi = float(lo_s), float(hi_s)
            except ValueError:
                result.add(token)  # a literal label with a dash, not a range
                continue
            for chapter in available_chapters:
                try:
                    value = float(chapter)
                except ValueError:
                    continue
                if lo <= value <= hi:
                    result.add(chapter)
            continue
        result.add(token)
    return sorted(result, key=chapter_sort_key)
