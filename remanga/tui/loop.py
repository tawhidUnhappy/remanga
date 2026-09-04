"""The shared moving parts of an interactive menu: what's visible after
filtering, where the cursor is, and the redraw/read-key loop around both.

`select`, `multiselect` and the ordered pipeline editor all differ in
exactly one thing - what a keypress *means* - so that is the only thing
they implement. Cursor movement, type-to-filter, scrolling a list longer
than the terminal, transient redraw, and terminal restoration all live here
once."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

from rich.live import Live

from remanga.console import console
from remanga.tui import keys
from remanga.tui.choices import Choice
from remanga.tui.frame import answer_line, menu_frame
from remanga.tui.result import PromptExit, is_cancel

# Leaves room for the title, the note/filter line, the two "N more" markers,
# the highlighted row's detail line and the footer, so a menu never grows
# taller than the window and starts scrolling the terminal itself.
_CHROME_LINES = 7
# Quit from any prompt, at any depth, without walking back out level by
# level. Not a plain letter: every menu filters as you type, so "q" has to
# stay available as a search character.
_EXIT_KEYS = ("ctrl-q",)
_MIN_PAGE = 3
_MAX_PAGE = 14


def default_page_size() -> int:
    return max(_MIN_PAGE, min(_MAX_PAGE, console.size.height - _CHROME_LINES))


class MenuState:
    """Live state of one open menu: the full choice list, the filter query,
    and the cursor. `visible` is always the filtered view, and the cursor is
    an index into *that* - so filtering never leaves the highlight pointing
    at a row nobody can see."""

    def __init__(self, choices: Sequence[Choice], *, cursor: int = 0, page_size: Optional[int] = None,
                 filterable: bool = True, space_filters: bool = False):
        self.choices: List[Choice] = list(choices)
        self.query = ""
        # A two-row yes/no menu has nothing worth filtering, and swallowing
        # "y"/"n" into a filter box there would break the very shortcuts
        # that make it fast (see remanga.tui.confirm).
        self.filterable = filterable
        # Whether Space types a space into the filter. True for single-select
        # menus, where filtering "Chapter Production" is impossible without
        # it; False for checklists, where Space is the toggle key.
        self.space_filters = space_filters
        self.page_size = page_size or default_page_size()
        self._visible: List[Choice] = list(self.choices)
        self.cursor = self._clamp(cursor)

    # --- view ---------------------------------------------------------
    @property
    def visible(self) -> List[Choice]:
        return self._visible

    @property
    def current(self) -> Optional[Choice]:
        if not self._visible:
            return None
        return self._visible[self.cursor]

    def _clamp(self, index: int) -> int:
        if not self._visible:
            return 0
        return max(0, min(index, len(self._visible) - 1))

    def _refilter(self) -> None:
        """Recomputes the visible list, keeping the currently highlighted
        row highlighted if it survived the filter - so refining a query
        narrows the list under a stable selection instead of snapping back
        to the top on every keystroke."""
        previous = self.current
        if self.query:
            needle = self.query.casefold()
            # Label matches first, then rows that only match on their hint or
            # badge. Hints are searchable on purpose ("blur", "zip", "gutter"
            # find the right row without knowing its name), but a row whose
            # *name* is what you typed must never sit below one that merely
            # mentions it in passing - typing "package" and pressing Enter
            # has to land on the `package` command, not on `crop`, whose
            # description happens to contain the word.
            by_label, by_text = [], []
            for choice in self.choices:
                if needle in choice.label.casefold():
                    by_label.append(choice)
                elif needle in f"{choice.hint} {choice.badge}".casefold():
                    by_text.append(choice)
            self._visible = by_label + by_text
        else:
            self._visible = list(self.choices)
        if previous is not None and previous in self._visible:
            self.cursor = self._visible.index(previous)
        else:
            self.cursor = 0
        self.skip_disabled(1)

    # --- movement -----------------------------------------------------
    def move(self, delta: int) -> None:
        """Moves the cursor, wrapping at both ends - a list is a ring, so
        Up from the first row lands on the last instead of doing nothing."""
        if not self._visible:
            return
        self.cursor = (self.cursor + delta) % len(self._visible)
        self.skip_disabled(1 if delta >= 0 else -1)

    def move_to(self, index: int) -> None:
        self.cursor = self._clamp(index)
        self.skip_disabled(1)

    def skip_disabled(self, direction: int) -> None:
        """Steps off a disabled row in `direction`. Bounded by the list
        length so an all-disabled list settles instead of spinning."""
        if not self._visible:
            return
        for _ in range(len(self._visible)):
            if not self._visible[self.cursor].disabled:
                return
            self.cursor = (self.cursor + direction) % len(self._visible)

    # --- keys handled the same way in every menu ----------------------
    def handle_common(self, key: str) -> bool:
        """Applies the navigation/filter keys every menu shares. Returns
        True if the key was consumed, so a caller's own handler only ever
        sees keys that are actually its business."""
        if key in (keys.UP, "ctrl-p"):
            self.move(-1)
        elif key in (keys.DOWN, keys.TAB, "ctrl-n"):
            self.move(1)
        elif key == keys.PAGE_UP:
            self.move(-self.page_size)
        elif key == keys.PAGE_DOWN:
            self.move(self.page_size)
        elif key == keys.HOME:
            self.move_to(0)
        elif key == keys.END:
            self.move_to(len(self._visible) - 1)
        elif key == keys.SPACE and self.filterable and self.space_filters and self.query:
            # Only mid-query: a bare Space on an untouched menu is a stray
            # keypress far more often than the start of a search for a name
            # beginning with a space.
            self.query += " "
            self._refilter()
        elif key == keys.BACKSPACE and self.filterable:
            if self.query:
                self.query = self.query[:-1]
                self._refilter()
        elif self.filterable and len(key) == 1 and key.isprintable():
            self.query += key
            self._refilter()
        else:
            return False
        return True

    def clear_query(self) -> bool:
        """Esc's first job: drop the filter. Returns whether there was one -
        if not, Esc means "back out of this menu" instead."""
        if not self.query:
            return False
        self.query = ""
        self._refilter()
        return True


def run_menu(
    state: MenuState,
    *,
    title: str,
    footer: str,
    note: str = "",
    checkable: bool = False,
    order_of: Optional[Callable[[], dict]] = None,
    on_key: Callable[[MenuState, str], Optional[tuple]],
    echo: Optional[Callable[[Any], str]] = None,
) -> Any:
    """Draws `state` and pumps keys through `on_key` until it answers.

    `on_key` returns None for "not finished" (whether or not it acted on the
    key) and a one-item tuple `(value,)` to finish with that value. The
    tuple wrapper is what lets a menu legitimately answer None, False or ""
    - all real answers elsewhere in remanga (an optional parameter left
    unset, "no BGM", a cleared field) - without them reading as "keep
    going".

    Rendering is transient: the menu redraws in place while open and leaves
    only a one-line record of the question and its answer behind (see
    `echo`), so a wizard session scrolls back as a readable list of
    decisions rather than dozens of redrawn menus.

    Ctrl+C raises KeyboardInterrupt with the terminal already restored -
    cli.py's SIGINT handler prints the same "production paused" message it
    always has."""
    with keys.key_reader() as reader:
        with Live(console=console, auto_refresh=False, transient=True) as live:
            while True:
                live.update(menu_frame(
                    title=title, choices=state.visible, cursor=state.cursor,
                    page_size=state.page_size, query=state.query, footer=footer,
                    note=note, checkable=checkable,
                    order=order_of() if order_of else None,
                ), refresh=True)

                key = reader.read_key()
                if key == keys.CTRL_C:
                    raise KeyboardInterrupt
                if key in _EXIT_KEYS:
                    raise PromptExit
                if key == keys.UNKNOWN:
                    continue  # mouse report/unsupported sequence - never a keystroke

                outcome = on_key(state, key)
                if outcome is not None:
                    value = outcome[0]
                    break
                state.handle_common(key)

    # Printed outside both context managers: a console.print issued while a
    # transient Live is open scrolls the live region rather than replacing
    # it, leaving the menu's last frame stranded above the answer.
    #
    # Backing out leaves no line at all - "✓ Project-wide  Back" reads like
    # a decision that was made, when in fact nothing happened.
    if echo is not None and not is_cancel(value):
        console.print(answer_line(title, echo(value)))
    return value
