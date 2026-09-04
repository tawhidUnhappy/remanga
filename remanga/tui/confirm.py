"""Yes/no, arrow-key style - the interactive counterpart to rich.prompt.Confirm.

Same two answers, but pre-highlighting the default rather than hiding it in
a "(Y/n)" suffix, able to show a `note` line of context under the question
(the path about to be overwritten, how many files a wipe would delete), and
answerable with either y/n or Enter-on-the-highlighted-row."""

from __future__ import annotations

from remanga.tui import fallback, keys
from remanga.tui.choices import Choice
from remanga.tui.loop import MenuState, run_menu

FOOTER = "↑↓ move · y/n · enter confirm · ctrl+q exit"


def confirm(
    title: str,
    *,
    default: bool = True,
    note: str = "",
    yes_label: str = "Yes",
    no_label: str = "No",
    yes_hint: str = "",
    no_hint: str = "",
    echo: bool = True,
) -> bool:
    """Returns True/False. Never CANCEL: Esc answers with the default rather
    than backing out, because a caller that asked a yes/no question has no
    third branch to take."""
    if not keys.is_interactive():
        return fallback.confirm(title, default=default)

    rows = [
        Choice(label=yes_label, hint=yes_hint, value=True),
        Choice(label=no_label, hint=no_hint, value=False),
    ]

    def on_key(state: MenuState, key: str):
        if key in ("y", "Y"):
            return (True,)
        if key in ("n", "N"):
            return (False,)
        if key == keys.ENTER:
            current = state.current
            return (bool(current.value),) if current else (default,)
        if key == keys.ESC:
            return (default,)
        return None

    return run_menu(
        MenuState(rows, cursor=0 if default else 1, filterable=False), title=title, footer=FOOTER,
        note=note, on_key=on_key,
        echo=(lambda value: yes_label if value else no_label) if echo else None,
    )
