"""Pick one thing from a list, with the arrow keys.

The single most-used prompt in the app: every category menu, command menu,
project picker, chapter picker, engine/resolution/language picker and
yes/no-with-context question is this function plus a list of Choices."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from remanga.tui import fallback, keys
from remanga.tui.choices import Choice, index_of_value
from remanga.tui.loop import MenuState, run_menu
from remanga.tui.result import CANCEL

FOOTER = "↑↓ move · enter select · type to filter · esc back"


def select(
    title: str,
    choices: Sequence[Choice],
    *,
    default: Any = None,
    default_index: int = 0,
    note: str = "",
    footer: str = FOOTER,
    back_label: Optional[str] = "Back",
    echo: bool = True,
) -> Any:
    """Returns the chosen Choice's `value`, or CANCEL if the user backed out.

    `default` pre-highlights whichever row carries that value - the "you are
    here" that makes Enter alone the right answer whenever the current
    setting is already correct. `back_label` adds an explicit last row for
    backing out (None removes it, for a question that must be answered);
    Esc does the same thing, after first clearing an active filter.

    Falls back to a numbered prompt on a non-tty stdin - see
    remanga.tui.fallback."""
    rows = list(choices)
    if not rows:
        return CANCEL

    start = index_of_value(rows, default, fallback=default_index) if default is not None else default_index
    if back_label:
        rows = rows + [Choice(label=back_label, value=CANCEL, hint="")]

    if not keys.is_interactive():
        return fallback.select(title, choices, default_index=start, back_label=back_label)

    def on_key(state: MenuState, key: str):
        if key == keys.ENTER:
            current = state.current
            if current is None or current.disabled:
                return None
            return (current.value,)
        if key == keys.ESC:
            if state.clear_query():
                return None
            return (CANCEL,) if back_label else None
        if key in (keys.LEFT,) and back_label:
            return (CANCEL,)
        return None

    return run_menu(
        MenuState(rows, cursor=start), title=title, footer=footer, note=note,
        on_key=on_key,
        echo=(lambda value: _echo_label(rows, value)) if echo else None,
    )


def _echo_label(rows: Sequence[Choice], value: Any) -> str:
    for row in rows:
        if row.value is value or row.value == value:
            return row.label
    return str(value)
