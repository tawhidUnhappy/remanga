"""Pick any number of things from a list - and, optionally, their order.

Two shapes, one implementation:

- plain checklist (`multiselect`). Space toggles.
- ordered checklist (`multiselect(ordered=True)`), where *sequence* is half
  the answer: rows show their run position (1., 2., 3.) instead of a tick,
  taken from the order they were checked in."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from remanga.tui import fallback, keys
from remanga.tui.choices import RESTING, Choice, exit_row, start_row
from remanga.tui.loop import MenuState, run_menu
from remanga.tui.result import CANCEL, EXIT, PromptExit

FOOTER = "↑↓ move · space toggle · ctrl+a all · ctrl+r none · enter confirm · esc back · ctrl+q exit"
ORDERED_FOOTER = ("↑↓ move · space add (order = run order) · ctrl+r clear · enter confirm · "
                  "esc back · ctrl+q exit")


def multiselect(
    title: str,
    choices: Sequence[Choice],
    *,
    ordered: bool = False,
    note: str = "",
    footer: str | None = None,
    allow_empty: bool = True,
    back_label: str | None = "Back",
    exit_label: str | None = "Exit remanga",
    echo: bool = True,
) -> Any:
    """Returns the checked values as a list (in check order when `ordered`,
    otherwise in list order), or CANCEL if the user backed out.

    Pre-check rows by setting `Choice.checked` - every caller in remanga
    does, so the menu opens showing the current state and Enter alone keeps
    it exactly as it is. `allow_empty=False` refuses to confirm an empty
    selection, for the answers where "none of them" isn't meaningful."""
    rows = [
        Choice(label=c.label, hint=c.hint, detail=c.detail, badge=c.badge,
               value=c.value, disabled=c.disabled, checked=c.checked, plain=c.plain)
        for c in choices
    ]
    if not rows:
        return []

    if not keys.is_interactive():
        return fallback.multiselect(title, rows, back_label=back_label, ordered=ordered)

    # Back and the quit row sit at the top, reachable with the arrow keys
    # without scrolling past a long list, but they are never checkable: Space
    # or Enter on them backs out or quits, ctrl+a skips them, and they can't
    # end up in the result. The cursor starts on the blank row above them, where
    # Space and Enter do nothing, so a key pressed straight away picks nothing.
    actions = [start_row()]
    if back_label:
        actions.append(Choice(label=back_label, value=CANCEL, plain=True))
    if exit_label:
        actions.append(exit_row(exit_label))
    rows = [*actions, *rows]

    # Check order, which is the run order in `ordered` mode. Seeded from
    # whatever arrived pre-checked so an existing order is kept.
    order: list[Any] = [c.value for c in rows if c.checked]

    def toggle(choice: Choice) -> None:
        if choice.disabled or choice.plain:
            return
        choice.checked = not choice.checked
        if choice.checked:
            if choice.value not in order:
                order.append(choice.value)
        elif choice.value in order:
            order.remove(choice.value)

    def set_all(checked: bool) -> None:
        order.clear()
        for choice in rows:
            if choice.disabled or choice.plain:
                continue
            choice.checked = checked
            if checked:
                order.append(choice.value)

    def order_of() -> dict[int, int]:
        """index-in-the-visible-list -> 1-based run position, rebuilt every
        redraw so it stays correct while the list is being filtered."""
        positions = {value: i + 1 for i, value in enumerate(order)}
        return {i: positions[c.value] for i, c in enumerate(state.visible) if c.value in positions}

    def result() -> list[Any]:
        if ordered:
            return list(order)
        return [c.value for c in rows if c.checked and not c.plain]

    def on_key(menu: MenuState, key: str):
        current = menu.current
        if current is not None and current.value is EXIT and key in (keys.ENTER, keys.SPACE, keys.RIGHT):
            raise PromptExit
        if current is not None and current.value is CANCEL and key in (keys.ENTER, keys.SPACE, keys.LEFT):
            return (CANCEL,)
        if key == keys.SPACE and current is not None:
            toggle(current)
            return None
        if key == keys.RIGHT and current is not None and not current.checked:
            toggle(current)
            return None
        if key == keys.LEFT and current is not None and current.checked:
            toggle(current)
            return None
        if key == "ctrl-a":
            set_all(True)
            return None
        if key == "ctrl-r":
            set_all(False)
            return None
        if key == keys.ENTER:
            if current is not None and current.value is RESTING:
                return None
            picked = result()
            if not picked and not allow_empty:
                return None
            return (picked,)
        if key == keys.ESC:
            return menu.escape(bool(back_label))
        return None

    state = MenuState(rows, cursor=0)
    return run_menu(
        state, title=title, footer=footer or (ORDERED_FOOTER if ordered else FOOTER),
        note=note, checkable=True, order_of=order_of if ordered else None,
        on_key=on_key,
        echo=(lambda values: ", ".join(_labels(rows, values)) or "nothing") if echo else None,
    )


def _labels(rows: Sequence[Choice], values: Any) -> list[str]:
    if values is CANCEL or not isinstance(values, list):
        return []
    by_value = {id(c.value): c.label for c in rows}
    return [
        by_value.get(id(value)) or next((c.label for c in rows if c.value == value), str(value))
        for value in values
    ]
