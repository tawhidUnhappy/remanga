"""Long-strip manga (webtoons): chapters that arrive as a few very tall images
and are read by scrolling down. MAGI (trained on printed pages) is no use on
them, so:

    layout.py   is this chapter a long strip
    runs.py     the downloaded images as strips of one width, in chapter rows
    gutters.py  which rows are gutters - each colour verified before it may cut
    detect.py   proposed panels: the art between gutters, tall ones split
    marks.py    the Strip Marker's marks (overlap allowed, optional sides)
    pages.py    marks packed into strip/ pages, never splitting touching ones
    crops.py    crops.json from those pages, cut exactly as marked
    tiles.py    the strip as small tiles for the browser tab
    build.py    keeps strip/ and crops.json in step with images and marks

The Strip Marker itself is remanga/webui/strip_*.py + static_strip/."""

from __future__ import annotations

from remanga.longstrip.build import ensure_strip, marking_pages_dir, proposed_marks, strip_dir, strip_panels
from remanga.longstrip.layout import LONG_STRIP, LONG_STRIP_TAG, PAGES, is_long_strip, source_pages
from remanga.longstrip.marks import marks_path, read_marks, write_marks
from remanga.longstrip.runs import runs_of
from remanga.longstrip.tiles import StripView

__all__ = ["LONG_STRIP", "LONG_STRIP_TAG", "PAGES", "StripView", "ensure_strip", "is_long_strip",
           "marking_pages_dir", "marks_path", "proposed_marks", "read_marks", "runs_of", "source_pages",
           "strip_dir", "strip_panels", "write_marks"]
