"""Long-strip manga (webtoons): chapters that arrive as a few very tall images
and are read by scrolling down. Their panels are found by mangaEasy's webtoon
splitter (split.py), not MAGI, and marked on the whole strip at once in the
Strip Marker (webui/strip_*.py); the strip is then re-cut into pages between
them (build.py), and from there they go through the same PDF and video as any
manga."""

from __future__ import annotations

from remanga.longstrip.build import (
    auto_panels,
    ensure_strip,
    image_layout,
    marking_pages_dir,
    read_strip_marks,
    strip_dir,
    strip_marks_path,
    strip_panels,
    write_strip_marks,
)
from remanga.longstrip.layout import LONG_STRIP, LONG_STRIP_TAG, PAGES, is_long_strip

__all__ = ["LONG_STRIP", "LONG_STRIP_TAG", "PAGES", "auto_panels", "ensure_strip", "image_layout", "is_long_strip",
           "marking_pages_dir", "read_strip_marks", "strip_dir", "strip_marks_path", "strip_panels",
           "write_strip_marks"]
