"""Pick any number of things from a list - and, optionally, their order.

Two shapes, one implementation:

- plain checklist (`multiselect`): what to keep during a wipe, which
  chapters to compile, which config switches are on. Space toggles.
- ordered checklist (`multiselect(ordered=True)`): the pipeline editor,
  where *sequence* is half the answer. Rows show their run position (1., 2.,
  3.) instead of a tick, taken from the order they were checked in, so
  building "crop, then tts, then render" is just checking three boxes in
  that order rather than typing a comma-separated list correctly."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from remanga.tui import fallback, keys
from remanga.tui.choices import Choice
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
    footer: Optional[str] = None,
    allow_empty: bool = True,
    back_label: Optional[str] = "Back",
    exit_label: Optional[str] = "Exit remanga",
    echo: bool = True,
) -> Any:
    """Returns the checked values as a list (in check order when `ordered`,
    otherwise in list order), or CANCEL if the user backed out.

    Pre-check rows by setting `Choice.checked` - every caller in remanga
    does, so the menu opens showing the current state and Enter alone keeps
    it exactly as it is. `allow_empty=False` refuses to confirm an empty
    selection, for the answers where "none of them" isn't meaningful (a
    pipeline with no steps)."""
    rows = [
        Choice(label=c.label, hint=c.hint, detail=c.detail, badge=c.badge,
               value=c.value, disabled=c.disabled, checked=c.checked, plain=c.plain)
        for c in choices
    ]
    if not rows:
        return []

    if not keys.is_interactive():
        return fallback.multiselect(title, rows, back_label=back_label, ordered=ordered)

    # The quit row rides along as an ordinary row so it's visible and
    # reachable with the arrow keys, but it is never checkable: Space and
    # Enter on it quit, ctrl+a skips it, and it can't end up in the result.
    if exit_label:
        rows = rows + [Choice(label=exit_label, hint="quit from here", value=EXIT, plain=True)]

    # Check order, which is the run order in `ordered` mode. Seeded from
    # whatever arrived pre-checked so an existing pipeline keeps its order.
    order: List[Any] = [c.value for c in rows if c.checked]

    def toggle(choice: Choice) -> None:
        if choice.disabled or choice.value is EXIT:
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
            if choice.disabled or choice.value is EXIT:
                continue
            choice.checked = checked
            if checked:
                order.append(choice.value)

    def order_of() -> Dict[int, int]:
        """index-in-the-visible-list -> 1-based run position, rebuilt every
        redraw so it stays correct while the list is being filtered."""
        positions = {value: i + 1 for i, value in enumerate(order)}
        return {i: positions[c.value] for i, c in enumerate(state.visible) if c.value in positions}

    def result() -> List[Any]:
        if ordered:
            return list(order)
        return [c.value for c in rows if c.checked and c.value is not EXIT]

    def on_key(menu: MenuState, key: str):
        current = menu.current
        if current is not None and current.value is EXIT and key in (keys.ENTER, keys.SPACE, keys.RIGHT):
            raise PromptExit
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
            picked = result()
            if not picked and not allow_empty:
                return None
            return (picked,)
        if key == keys.ESC:
            if menu.clear_query():
                return None
            return (CANCEL,) if back_label else None
        return None

    state = MenuState(rows)
    return run_menu(
        state, title=title, footer=footer or (ORDERED_FOOTER if ordered else FOOTER),
        note=note, checkable=True, order_of=order_of if ordered else None,
        on_key=on_key,
        echo=(lambda values: ", ".join(_labels(rows, values)) or "nothing") if echo else None,
    )


def _labels(rows: Sequence[Choice], values: Any) -> List[str]:
    if values is CANCEL or not isinstance(values, list):
        return []
    by_value = {id(c.value): c.label for c in rows}
    labels = []
    for value in values:
        labels.append(by_value.get(id(value)) or next((c.label for c in rows if c.value == value), str(value)))
    return labels
