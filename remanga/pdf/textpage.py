"""The PDF's text page: left-aligned lines of Helvetica (a standard-14 font,
nothing to embed), white on black, the type scaled to the page."""

from __future__ import annotations

from collections.abc import Sequence

# A text page's own size in points (1/72 inch), whatever size the images
# are: twice US Letter each way, with the type kept at 11pt, so a page holds
# four times what a letter page does. An LLM prices a PDF page the same
# whatever it shows (Gemini 3: 560 tokens) and reads a text page's words
# from its text layer, so fewer, fuller text pages cost less and lose nothing.
TEXT_PAGE_SIZE = (1224, 1584)


TEXT_FONT = "Helvetica"


_TEXT_SIZE = 11


_TEXT_LEADING = 15


_TEXT_MARGIN = 54


def _escape_pdf_text(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def text_layout(page_w: int, page_h: int) -> tuple[int, int, int, int]:
    """Type size, leading, margin and lines per page for a page this big."""
    return _TEXT_SIZE, _TEXT_LEADING, _TEXT_MARGIN, max(1, (page_h - 2 * _TEXT_MARGIN) // _TEXT_LEADING)


def text_page_content(lines: Sequence[str], page_w: int, page_h: int) -> bytes:
    """A text page: black, like the panel pages, with the text in white."""
    size, leading, margin, _ = text_layout(page_w, page_h)
    x, y = margin, page_h - margin - size
    parts = [f"0 0 0 rg 0 0 {page_w} {page_h} re f",  # the same black as the panel pages
             "1 1 1 rg",                              # so the text has to be white
             f"BT /F1 {size} Tf {leading} TL {x} {y} Td"]
    for i, line in enumerate(lines):
        if i > 0:
            parts.append("T*")
        # Standard-14 Helvetica in WinAnsiEncoding (writer.py) covers
        # Windows-1252 - Latin-1 plus curly quotes and dashes. This text page
        # is metadata (chapter identity, story so far), not the pages, so a
        # character beyond that becomes "?" rather than pulling in a
        # Unicode-capable embedded font for one info page. Never affects the
        # page images, which stay exact regardless.
        parts.append(f"({_escape_pdf_text(line)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("cp1252", errors="replace")
