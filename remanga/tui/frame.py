"""How every dynamic menu looks on screen.

One renderer for all of them (single-select, checklist, confirm) so the
pointer, the checkbox column, the dim hint, the "N more" scroll markers and
the key-hint footer are literally the same code in every menu rather than
five near-identical print loops that drifted apart. Callers describe *what*
is on screen (choices, where the cursor is, what's checked); this decides
how it's drawn.

Everything is built as `rich.text.Text` with explicit styles rather than
markup strings. Labels routinely carry user data - project names, chapter
folders, filenames like "Title [Complete].png" - and Rich would read that
'[' as the start of a style tag, swallowing the rest of the line or raising
MarkupError. Text.append never interprets its argument, so no caller has to
remember to escape anything."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from rich.console import Group
from rich.text import Text

from remanga.tui.choices import Choice

POINTER = "❯"
CHECKED = "◉"
UNCHECKED = "○"

_STYLE_TITLE = "bold"
_STYLE_MARK = "bold cyan"
_STYLE_ACTIVE = "bold cyan"
_STYLE_HINT = "dim"
_STYLE_BADGE = "yellow"
_STYLE_ON = "green"
_STYLE_DISABLED = "dim strike"


def window_bounds(cursor: int, total: int, page_size: int) -> "tuple[int, int]":
    """The slice of a long list to actually draw, kept centered-ish on the
    cursor. Returns (start, end) as a half-open range; both are clamped so
    the window never runs past either end of the list, which is what stops
    the last page from rendering half-empty."""
    if total <= page_size:
        return 0, total
    half = page_size // 2
    start = max(0, min(cursor - half, total - page_size))
    return start, start + page_size


def _row(choice: Choice, *, active: bool, checkable: bool, order: Optional[int]) -> Text:
    line = Text()
    line.append(f"{POINTER} " if active else "  ", style=_STYLE_MARK if active else "")

    if checkable:
        if order is not None:
            # Ordered checklists (pipeline steps) show the run position
            # instead of a plain tick - the number IS the information.
            line.append(f"{order}. " if choice.checked else "-- ", style=_STYLE_ON if choice.checked else _STYLE_HINT)
        else:
            line.append(f"{CHECKED} " if choice.checked else f"{UNCHECKED} ",
                        style=_STYLE_ON if choice.checked else _STYLE_HINT)

    if choice.badge:
        line.append(f"[{choice.badge}] ", style=_STYLE_BADGE)

    if choice.disabled:
        line.append(choice.label, style=_STYLE_DISABLED)
    else:
        line.append(choice.label, style=_STYLE_ACTIVE if active else "")

    if choice.hint:
        line.append("  ")
        line.append(choice.hint, style=_STYLE_HINT)
    return line


def menu_frame(
    *,
    title: str,
    choices: Sequence[Choice],
    cursor: int,
    page_size: int,
    query: str = "",
    footer: str = "",
    note: str = "",
    checkable: bool = False,
    order: Optional[Dict[int, int]] = None,
    empty_text: str = "no matches",
) -> Group:
    """Assembles one complete menu screen.

    `order` (index -> 1-based position) turns the checkbox column into
    ordered run positions, for the pipeline editor where *sequence* is half
    the answer. `note` is a single line under the title for context the user
    needs while choosing (a path, a warning, a count)."""
    lines: List[Text] = []

    header = Text()
    header.append("? ", style=_STYLE_MARK)
    header.append(title, style=_STYLE_TITLE)
    if query:
        header.append("  filter: ", style=_STYLE_HINT)
        header.append(query, style="yellow")
    lines.append(header)

    if note:
        lines.append(Text(f"  {note}", style=_STYLE_HINT))

    if not choices:
        lines.append(Text(f"  {empty_text}", style=_STYLE_HINT))
    else:
        start, end = window_bounds(cursor, len(choices), page_size)
        if start > 0:
            lines.append(Text(f"  ↑ {start} more", style=_STYLE_HINT))
        for i in range(start, end):
            lines.append(_row(
                choices[i], active=(i == cursor), checkable=checkable,
                order=(order or {}).get(i) if order is not None else None,
            ))
        remaining = len(choices) - end
        if remaining > 0:
            lines.append(Text(f"  ↓ {remaining} more", style=_STYLE_HINT))

        detail = choices[cursor].detail if 0 <= cursor < len(choices) else ""
        if detail:
            lines.append(Text(f"  {detail}", style=_STYLE_HINT))

    if footer:
        lines.append(Text(f"  {footer}", style=_STYLE_HINT))
    return Group(*lines)


def answer_line(title: str, answer: str) -> Text:
    """The one line left behind in the scrollback once a menu closes - the
    question and what was picked, nothing else. Menus render transiently
    (they redraw in place while open), so without this a finished wizard
    would scroll back as a list of results with no record of what was being
    asked."""
    line = Text()
    line.append("✓ ", style=_STYLE_ON)
    line.append(title, style=_STYLE_TITLE)
    line.append("  ")
    line.append(answer, style="cyan")
    return line
