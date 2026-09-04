"""Pick one thing from a list, with the arrow keys.

The single most-used prompt in the app: every category menu, command menu,
project picker, chapter picker, engine/resolution/language picker and
yes/no-with-context question is this function plus a list of Choices."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from remanga.tui import fallback, keys
from remanga.tui.choices import Choice, index_of_value
from remanga.tui.frame import numbered_rows
from remanga.tui.loop import MenuState, run_menu
from remanga.tui.result import CANCEL, EXIT, PromptExit

FOOTER = "↑↓ move · enter select · type to filter · esc back · ctrl+q exit"
# Same convention the non-tty fallback has always printed (1..N for the
# items, 0 for back), so the two ways of answering the same menu don't
# disagree about what a digit means.
NUMBERED_FOOTER = "type 1-{count} · ↑↓ move · enter select · 0 or esc back · ctrl+q exit"


def select(
    title: str,
    choices: Sequence[Choice],
    *,
    default: Any = None,
    default_index: int = 0,
    note: str = "",
    numbered: bool = False,
    footer: Optional[str] = None,
    back_label: Optional[str] = "Back",
    exit_label: Optional[str] = "Exit remanga",
    echo: bool = True,
) -> Any:
    """Returns the chosen Choice's `value`, or CANCEL if the user backed out.

    `default` pre-highlights whichever row carries that value - the "you are
    here" that makes Enter alone the right answer whenever the current
    setting is already correct. `back_label` adds an explicit last row for
    backing out (None removes it, for a question that must be answered);
    Esc does the same thing, after first clearing an active filter.

    `exit_label` adds the always-present quit row (ctrl+q does the same),
    which raises PromptExit rather than returning - see remanga.tui.result.
    Pass None only for a prompt where quitting outright makes no sense.

    `numbered` puts 1., 2., 3. in front of the rows and makes those digits
    pick them outright - one keystroke, no arrowing, no Enter - with 0 for
    back, the same convention the non-tty fallback prints. For a short,
    stable list (the TTS engines, a handful of presets) that's the fastest
    way to answer and the easiest to read out of a screenshot. It turns
    type-to-filter off for that menu, since the digits are now shortcuts and
    a five-row list has nothing worth filtering; leave it off for anything
    long or searchable, where filtering is the better way in. Only the first
    nine rows are reachable by digit - the arrow keys still reach the rest.

    Falls back to a numbered prompt on a non-tty stdin - see
    remanga.tui.fallback."""
    rows = list(choices)
    if not rows:
        return CANCEL

    start = index_of_value(rows, default, fallback=default_index) if default is not None else default_index
    # `plain` keeps the two action rows out of the numbering (see
    # frame.numbered_rows); it has no other effect on a single-select menu.
    if back_label:
        rows = rows + [Choice(label=back_label, value=CANCEL, hint="", plain=True)]
    if exit_label:
        rows = rows + [Choice(label=exit_label, value=EXIT, hint="quit from here", plain=True)]

    if footer is None:
        footer = NUMBERED_FOOTER.format(count=min(len(choices), 9)) if numbered else FOOTER

    if not keys.is_interactive():
        return fallback.select(title, choices, default_index=start, back_label=back_label,
                               exit_label=exit_label)

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
        if numbered and len(key) == 1 and key.isdigit():
            if key == "0":
                return (CANCEL,) if back_label else None
            picked_row = _row_numbered(state, int(key))
            if picked_row is not None:
                return (picked_row.value,)
            # A digit past the end of the list does nothing at all: with
            # filtering off there's nowhere for it to go, and silently moving
            # the cursor somewhere unrelated would be worse than ignoring it.
            return None
        return None

    picked = run_menu(
        MenuState(rows, cursor=start, space_filters=True, filterable=not numbered),
        title=title, footer=footer, note=note, numbered=numbered,
        on_key=on_key,
        echo=(lambda value: _echo_label(rows, value)) if echo else None,
    )
    if picked is EXIT:
        raise PromptExit
    return picked


def _row_numbered(state: MenuState, number: int) -> Optional[Choice]:
    """The row currently showing `number`, or None if nothing does. Resolved
    against the same numbering the frame drew (frame.numbered_rows over the
    visible rows), never against the raw list index - otherwise a disabled
    row would make the digit you press and the digit you see drift apart."""
    for index, shown in numbered_rows(state.visible).items():
        if shown == number:
            return state.visible[index]
    return None


def _echo_label(rows: Sequence[Choice], value: Any) -> str:
    for row in rows:
        if row.value is value or row.value == value:
            return row.label
    return str(value)
