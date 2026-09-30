"""Long-strip manga (webtoons): chapters that arrive as a few very tall images
and are read by scrolling down. Their panels are found by mangaEasy's webtoon
splitter (split.py), not MAGI, and the strip is re-cut into pages between
them (build.py); from there they go through the same marking, PDF and video
as any manga."""

from __future__ import annotations

from remanga.longstrip.build import ensure_strip, marking_pages_dir, strip_dir, strip_panels
from remanga.longstrip.layout import LONG_STRIP, LONG_STRIP_TAG, PAGES, is_long_strip

__all__ = ["LONG_STRIP", "LONG_STRIP_TAG", "PAGES", "ensure_strip", "is_long_strip", "marking_pages_dir",
           "strip_dir", "strip_panels"]
