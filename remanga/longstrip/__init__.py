"""Long-strip manga (webtoons): chapters that arrive as a few very tall images
and are read by scrolling down. They are re-cut into pages between their
panels, and from there on go through the same marking, PDF and video as any
manga - see build.py."""

from __future__ import annotations

from remanga.longstrip.build import ensure_strip, marking_pages_dir, strip_dir
from remanga.longstrip.layout import LONG_STRIP, LONG_STRIP_TAG, PAGES, is_long_strip

__all__ = ["LONG_STRIP", "LONG_STRIP_TAG", "PAGES", "ensure_strip", "is_long_strip", "marking_pages_dir",
           "strip_dir"]
