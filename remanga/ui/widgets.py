"""Textual widgets with remanga's safety rule built in.

Nothing is highlighted until you ask for it: a list opens with no row picked,
so an Enter pressed before looking does nothing (user request). The first
arrow key or click highlights a row; Enter or a DOUBLE click chooses it. A
single click only moves the highlight - clicking around never starts work."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable, Input, OptionList, Static


class TopBar(Horizontal):
    """Where you are on the left, a short fact on the right."""

    DEFAULT_CSS = """
    TopBar { dock: top; height: 2; padding: 0 1; border-bottom: solid $panel-lighten-2; }
    TopBar #where { width: 1fr; text-wrap: nowrap; text-overflow: ellipsis; }
    TopBar #info { width: auto; color: $text-muted; }
    """

    def __init__(self, path: list[str], info: str = "") -> None:
        super().__init__()
        self.path, self._info = path, info

    def compose(self) -> ComposeResult:
        where = Text()
        for i, part in enumerate(self.path):
            if i:
                where.append("  ›  ", style="dim")
            where.append(part, style="bold" if i == len(self.path) - 1 else "dim")
        yield Static(where, id="where")
        yield Static(self._info, id="info")

    def set_info(self, info: str) -> None:
        self.query_one("#info", Static).update(info)


class SafeTable(DataTable):
    """A row table that starts with no row highlighted."""

    # Shown in the footer (DataTable's own Enter binding is hidden, and a
    # focused widget's binding hides the screen's).
    BINDINGS = [Binding("enter", "select_cursor", "Choose")]

    DEFAULT_CSS = """
    SafeTable { height: 1fr; }
    """

    class MarkClicked(Message):
        """The first column of a table with `mark_column` was clicked."""

        def __init__(self, row: int) -> None:
            super().__init__()
            self.row = row

    def __init__(self, *, mark_column: bool = False, **kwargs) -> None:
        super().__init__(cursor_type="row", show_cursor=False, zebra_stripes=False, **kwargs)
        self.mark_column = mark_column

    @property
    def picked_row(self) -> int | None:
        """The highlighted row, or None before an arrow key or click."""
        return self.cursor_row if self.show_cursor and self.row_count else None

    def _arm(self, row: int) -> bool:
        """Shows the cursor on `row` if it isn't shown yet; True if it wasn't."""
        if self.show_cursor or not self.row_count:
            return False
        self.show_cursor = True
        self.move_cursor(row=row)
        return True

    def action_cursor_down(self) -> None:
        if not self._arm(0):
            super().action_cursor_down()

    def action_cursor_up(self) -> None:
        if not self._arm(self.row_count - 1):
            super().action_cursor_up()

    def action_page_down(self) -> None:
        if not self._arm(0):
            super().action_page_down()

    def action_page_up(self) -> None:
        if not self._arm(0):
            super().action_page_up()

    def action_scroll_home(self) -> None:
        if not self._arm(0):
            super().action_scroll_home()

    def action_scroll_end(self) -> None:
        if not self._arm(self.row_count - 1):
            super().action_scroll_end()

    def action_select_cursor(self) -> None:
        if self.show_cursor:
            super().action_select_cursor()

    async def _on_click(self, event: events.Click) -> None:
        meta = event.style.meta
        row = meta.get("row")
        if row is None or row < 0 or meta.get("out_of_bounds", False):
            await super()._on_click(event)  # header clicks and the like
            return
        # Textual would also run DataTable's own click handler (which chooses
        # on the second single click) - prevent_default stops that.
        event.prevent_default()
        event.stop()
        self.show_cursor = True
        self.cursor_coordinate = Coordinate(row, max(0, meta.get("column", 0)))
        if self.mark_column and meta.get("column") == 0:
            self.post_message(self.MarkClicked(row))
        elif event.chain >= 2:
            self._post_selected_message()


class SafeOptionList(OptionList):
    """Dialog options: none highlighted at first, double click to choose."""

    BINDINGS = [Binding("enter", "select", "Choose")]

    def __init__(self, *options, **kwargs) -> None:
        super().__init__(*options, **kwargs)
        self.highlighted = None  # OptionList highlights the first option itself

    def action_cursor_up(self) -> None:
        if self.highlighted is None:
            self.action_last()
        else:
            super().action_cursor_up()

    async def _on_click(self, event: events.Click) -> None:
        event.prevent_default()  # not OptionList's handler, which chooses on one click
        clicked = event.style.meta.get("option")
        if clicked is None or self._options[clicked].disabled:
            return
        self.highlighted = clicked
        if event.chain >= 2:
            self.action_select()

    def action_select(self) -> None:
        if self.highlighted is not None:
            super().action_select()


class TextInput(Input):
    BINDINGS = [Binding("enter", "submit", "OK")]
