"""Zero-padded file naming shared across the whole pipeline, so downloader,
cropper, sheet generator, video compose, and every LLM upload bundle all
agree on the same filenames without duplicating the format logic:

- A downloaded page: `{chapter}_{page}` (e.g. `001_007.png`).
- A cropped panel: `{chapter}_{page}_{panel}` (e.g. `001_007_02.png`) -
  `panel` numbers reset to 1 at the start of every page, not across the
  whole chapter, so the number always answers "which panel on this page."
- A contact sheet: `{chapter}_{start_panel_name}_{end_panel_name}` (e.g.
  `001_001_001_01_004_02.png`) - named after the range of panel names it
  actually contains, not a running sheet index.

Chapter/page/panel numbers are all zero-padded (see the WIDTH constants
below) so filenames sort correctly in a plain alphabetical directory
listing - which is also the order the rest of the pipeline (manifest
writers, video compose, LLM bundles) relies on.
"""

from __future__ import annotations

CHAPTER_WIDTH = 3
PAGE_WIDTH = 3
PANEL_WIDTH = 2


def fmt_chapter(chapter_num) -> str:
    """Zero-pads a chapter number if it's a plain integer (`"7"` -> `"007"`);
    leaves anything else (e.g. `"10.5"`, a special/bonus chapter label)
    untouched rather than mangling it."""
    s = str(chapter_num).strip()
    return s.zfill(CHAPTER_WIDTH) if s.isdigit() else s


def fmt_page(page_index: int) -> str:
    return str(int(page_index)).zfill(PAGE_WIDTH)


def fmt_panel(panel_index: int) -> str:
    return str(int(panel_index)).zfill(PANEL_WIDTH)


def page_stem(chapter_num, page_index: int) -> str:
    """The filename stem (no extension) for a downloaded page."""
    return f"{fmt_chapter(chapter_num)}_{fmt_page(page_index)}"


def panel_stem(chapter_num, page_index: int, panel_index: int) -> str:
    """The filename stem (no extension) for one cropped panel - `panel_index`
    is 1-based and counts panels *on that page only*."""
    return f"{page_stem(chapter_num, page_index)}_{fmt_panel(panel_index)}"


def sheet_stem(chapter_num, start_panel_name: str, end_panel_name: str) -> str:
    """The filename stem (no extension) for one contact sheet, named after
    the inclusive range of panel names it contains - `{chapter}_{start}_
    {end}`. Panel names already start with the same chapter prefix (see
    panel_stem), so it's never duplicated here - the chapter only appears
    once, at the front."""
    chapter = fmt_chapter(chapter_num)
    prefix = f"{chapter}_"
    if start_panel_name.startswith(prefix):
        start_panel_name = start_panel_name[len(prefix):]
    if end_panel_name.startswith(prefix):
        end_panel_name = end_panel_name[len(prefix):]
    return f"{chapter}_{start_panel_name}_{end_panel_name}"
