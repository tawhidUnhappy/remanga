"""The PDF's text page: left-aligned lines of Helvetica (a standard-14 font,
nothing to embed), white on black, the type scaled to the page."""

from __future__ import annotations

from collections.abc import Sequence

# US Letter in points (1/72 inch): what the text page's type was sized for,
# and the page size when a PDF has no panels at all. Every page of a real
# chapter is the biggest panel's size instead (1 image pixel = 1 PDF point),
# so no image is ever rescaled.
TEXT_PAGE_SIZE = (612, 792)


TEXT_FONT = "Helvetica"


_TEXT_SIZE = 11


_TEXT_LEADING = 15


_TEXT_MARGIN = 54


def _escape_pdf_text(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def text_layout(page_w: int, page_h: int) -> tuple[int, int, int, int]:
    """Type size, leading, margin and lines per page for a page this big.

    The base is the letter-sized page these numbers were chosen for; a bigger
    page scales them by the same factor rather than leaving 11pt text adrift
    in a corner of it."""
    scale = max(1.0, min(page_w / TEXT_PAGE_SIZE[0], page_h / TEXT_PAGE_SIZE[1]))
    size, leading, margin = round(_TEXT_SIZE * scale), round(_TEXT_LEADING * scale), round(_TEXT_MARGIN * scale)
    return size, leading, margin, max(1, (page_h - 2 * margin) // leading)


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
        # Standard-14 Helvetica only covers Latin-1 - this text page is
        # metadata (chapter identity, story so far), not the pages, so a
        # non-Latin-1 character here becomes "?" rather than pulling in a
        # Unicode-capable embedded font for one info page. Never affects the
        # page images, which stay exact regardless.
        parts.append(f"({_escape_pdf_text(line)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", errors="replace")
