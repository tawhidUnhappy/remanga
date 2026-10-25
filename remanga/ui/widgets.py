"""Textual widgets with remanga's safety rule built in.

Nothing is highlighted until you ask for it: a list opens with no row picked,
so an Enter pressed before looking does nothing (user request). The first
arrow key or click highlights a row; Enter or a DOUBLE click chooses it. A
single click only moves the highlight - clicking around never starts work."""

from __future__ import annotations

from dataclasses import dataclass

from rich.style import Style
from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable, Input, OptionList, Static

PATH_SEPARATOR = "  ›  "


def _path_text(path: list[str], width: int) -> Text:
    """The path, as much of it as fits `width`: the place you are in is kept
    whole for as long as it can be, and the places above it give way first -
    each collapsed to "…", oldest first, then the last one cut short."""
    parts = list(path)
    for collapse in range(len(parts)):
        shown = ["…" if 0 < i <= collapse and i < len(parts) - 1 else part for i, part in enumerate(parts)]
        if len(PATH_SEPARATOR.join(shown)) <= width or collapse >= len(parts) - 2:
            parts = shown
            break
    text = Text()
    for i, part in enumerate(parts):
        if i:
            text.append(PATH_SEPARATOR, style="dim")
        text.append(part, style="bold" if i == len(parts) - 1 else "dim")
    text.truncate(max(1, width), overflow="ellipsis")
    return text


class TopBar(Static):
    """Where you are, and a short fact beside it - on the same line when both
    fit, the fact on a line of its own when they don't, so neither is ever
    cut to make room for the other."""

    DEFAULT_CSS = """
    TopBar { dock: top; height: auto; padding: 0 1; border-bottom: solid $panel-lighten-2; }
    """

    def __init__(self, path: list[str], info: str = "") -> None:
        super().__init__()
        self.path, self._info = path, info

    def on_mount(self) -> None:
        self._draw()

    def on_resize(self) -> None:
        self._draw()

    def set_info(self, info: str) -> None:
        self._info = info
        self._draw()

    def _draw(self) -> None:
        if not self.is_attached:
            return
        width = self.content_region.width or self.app.size.width - 2
        full = PATH_SEPARATOR.join(self.path)
        info = Text(self._info, style="dim")
        if not self._info:
            self.update(_path_text(self.path, width))
        elif len(full) + 3 + len(self._info) <= width:
            line = _path_text(self.path, width)
            line.append(" " * (width - len(full) - len(self._info)))
            self.update(line + info)
        else:
            self.update(Text("\n").join([_path_text(self.path, width), info]))


class KeyBar(Static):
    """The keys this screen takes, like Textual's Footer - but wrapped onto
    as many lines as the window needs, so a narrow window loses no key off
    its right edge. A key is never split from what it does. Click one to
    press it."""

    DEFAULT_CSS = """
    KeyBar { dock: bottom; height: auto; padding: 0 1; background: $footer-background; }
    """

    _line_count = 1

    def on_mount(self) -> None:
        self.screen.bindings_updated_signal.subscribe(self, self._bindings_changed)
        self.call_after_refresh(self._draw)

    def on_unmount(self) -> None:
        self.screen.bindings_updated_signal.unsubscribe(self)

    def on_resize(self) -> None:
        self._draw()

    def _bindings_changed(self, screen) -> None:
        if self.is_attached and screen is self.screen:
            self.call_after_refresh(self._draw)

    def _items(self) -> list[Text]:
        """One "key what-it-does" per action, in the screen's order; several
        keys for one action (shift+up and shift+down) show as the first."""
        # The look's own footer colours (ui/look.py).
        colours = self.app.theme_variables
        key_style = Style(color=colours.get("footer-key-foreground"), bold=True)
        label_style = Style(color=colours.get("footer-description-foreground"))
        seen, items = set(), []
        for _node, binding, enabled, _tooltip in self.screen.active_bindings.values():
            if not binding.show or binding.action in seen:
                continue
            seen.add(binding.action)
            item = Text.assemble((self.app.get_key_display(binding), key_style), " ",
                                 (binding.description, label_style))
            if not enabled:
                item.stylize("dim")
            item.stylize(Style(meta={"@click": f"app.simulate_key({binding.key.split(',')[0]!r})"}))
            items.append(item)
        return items

    def _draw(self) -> None:
        if not self.is_attached:   # a redraw asked for just before its screen closed
            return
        width = max(1, self.content_region.width or self.app.size.width - 2)
        lines: list[Text] = []
        line = Text()
        for item in self._items():
            item.truncate(width, overflow="ellipsis")
            if line and line.cell_len + 2 + item.cell_len > width:
                lines.append(line)
                line = Text()
            if line:
                line.append("  ")
            line.append_text(item)
        lines.append(line)
        self.update(Text("\n").join(lines))
        if len(lines) != self._line_count:
            # A dialog sizes itself around this bar (dialogs/fit.py): when it
            # gains or loses a line, the dialog measures again.
            self._line_count = len(lines)
            refit = getattr(self.screen, "_fit", None)
            if callable(refit):
                self.call_after_refresh(refit)


class RowDetail(Static):
    """The highlighted row's text that its table had to cut short - a column
    too narrow for a long title, or one left out of a narrow window - shown
    here in full, so nothing in a table is out of reach. Empty, and no rows
    tall, while everything fits. A screen puts one under its table."""

    DEFAULT_CSS = """
    RowDetail { height: auto; max-height: 4; padding: 0 1; color: $text-muted; overflow-y: auto;
                border-top: solid $panel-lighten-2; scrollbar-size-vertical: 1; }
    RowDetail.-empty { display: none; }
    """

    def show(self, text: Text | None) -> None:
        self.set_class(not text, "-empty")
        # Never more than a quarter of the window, so the table keeps its
        # rows; what doesn't fit scrolls.
        if self.is_attached:
            self.styles.max_height = max(1, min(4, self.screen.size.height // 4))
        self.update(text or "")


@dataclass
class _Column:
    label: str
    width: int | None   # None: a text column, as wide as the window lets it be
    key: str | None
    drop: int           # 0: always shown; otherwise left out of a narrow window, highest first


# The narrowest a text column is squeezed to before a column is left out instead.
MIN_TEXT_WIDTH = 10


def _plain(cell) -> str:
    return cell.plain if isinstance(cell, Text) else str(cell)


def _fitted(cell, width: int):
    """A cell cut to `width` with an ellipsis, so a cut is seen as one -
    DataTable alone crops mid-word with nothing to say so."""
    if len(_plain(cell)) <= width:
        return cell
    text = cell.copy() if isinstance(cell, Text) else Text(str(cell))
    text.truncate(width, overflow="ellipsis")
    return text


class SafeTable(DataTable):
    """A row table that starts with no row highlighted - and fits the window
    at any size: no column runs off the right edge. A column with a width
    keeps it (or less, when nothing in it needs that much); a text column
    (width None) takes what is left. When even that does not fit, the columns
    a screen marked `drop` are left out, highest first. Whatever a cell could
    not show - cut short, or its column left out - the highlighted row's
    RowDetail under the table shows in full."""

    # Shown in the footer (DataTable's own Enter binding is hidden, and a
    # focused widget's binding hides the screen's).
    BINDINGS = [Binding("enter", "select_cursor", "Choose")]

    DEFAULT_CSS = """
    SafeTable { height: 1fr; overflow-x: hidden; }
    """

    class MarkClicked(Message):
        """The first column of a table with `mark_column` was clicked."""

        def __init__(self, row: int) -> None:
            super().__init__()
            self.row = row

    def __init__(self, *, mark_column: bool = False, **kwargs) -> None:
        super().__init__(cursor_type="row", show_cursor=False, zebra_stripes=False, **kwargs)
        self.mark_column = mark_column
        self._columns: list[_Column] = []
        self._cells: list[list] = []          # every row's cells, every column
        self._shown: list[int] = []           # the columns on screen, by index into _columns
        self._widths: dict[int, int] = {}
        self._fitted_for: tuple | None = None

    # --- the columns a screen adds, and the ones the window has room for ---
    def add_column(self, label, *, width: int | None = None, key: str | None = None,
                   default=None, drop: int = 0):
        self._columns.append(_Column(_plain(label), width, key, drop))
        self._shown.append(len(self._columns) - 1)
        self._widths[len(self._columns) - 1] = width or len(_plain(label))
        return super().add_column(label, width=width, key=key, default=default)

    def add_row(self, *cells, height: int | None = 1, key: str | None = None, label=None):
        self._cells.append(list(cells))
        row_key = super().add_row(*(cells[i] for i in self._shown), height=height, key=key, label=label)
        self.call_after_refresh(self._fit)
        return row_key

    def clear(self, columns: bool = False):
        self._cells = []
        if columns:
            self._columns, self._shown, self._widths = [], [], {}
        self._fitted_for = None
        return super().clear(columns=columns)

    def update_cell_at(self, coordinate: Coordinate, value, *, update_width: bool = False) -> None:
        """`coordinate`'s column counts every column, shown or not."""
        self._cells[coordinate.row][coordinate.column] = value
        if coordinate.column in self._shown:
            super().update_cell_at(Coordinate(coordinate.row, self._shown.index(coordinate.column)),
                                   _fitted(value, self._widths.get(coordinate.column, len(_plain(value)))))
        self._show_detail()

    def on_resize(self) -> None:
        self._fit()

    def _natural(self, index: int) -> int:
        """How wide a column's widest cell (or its heading) is."""
        widths = [len(_plain(row[index])) for row in self._cells if index < len(row)]
        return max([len(self._columns[index].label), *widths])

    def _plan(self, room: int) -> tuple[list[int], dict[int, int]]:
        """Which columns fit `room` cells, and how wide each one is."""
        pad = 2 * self.cell_padding
        natural = {i: self._natural(i) for i in range(len(self._columns))}
        fixed = {i: min(c.width, natural[i]) for i, c in enumerate(self._columns) if c.width is not None}
        shown = list(range(len(self._columns)))

        def need(cols) -> int:
            return sum(fixed[i] if i in fixed else min(natural[i], MIN_TEXT_WIDTH) for i in cols) + pad * len(cols)

        while need(shown) > room:
            droppable = [i for i in shown if self._columns[i].drop]
            if not droppable:
                break
            shown.remove(max(droppable, key=lambda i: (self._columns[i].drop, i)))

        widths = {i: fixed[i] for i in shown if i in fixed}
        text = [i for i in shown if i not in fixed]
        left = room - sum(widths.values()) - pad * len(shown)
        total = sum(natural[i] for i in text)
        if total <= left:
            # Everything fits as it is: the room to spare goes to the columns
            # with a width that their cells still overflow, left to right.
            widths.update({i: natural[i] for i in text})
            spare = left - total
            for i in sorted(widths):
                grow = min(spare, natural[i] - widths[i])
                if grow > 0:
                    widths[i] += grow
                    spare -= grow
        elif text:
            for i in text:
                widths[i] = max(3, left * natural[i] // max(total, 1))
        elif left < 0:
            # Nothing left to leave out, and still too wide: the widest give way.
            for i in sorted(widths, key=widths.get, reverse=True):
                cut = min(-left, widths[i] - 3)
                widths[i] -= cut
                left += cut
        return shown, widths

    def _fit(self) -> None:
        """Lays the columns out for the window as it is now - rebuilt only
        when what fits has changed."""
        if not self.is_attached or not self._columns or self.size.width <= 0:
            return
        room = self.size.width - (self.scrollbar_size_vertical if self.row_count > self.size.height - 1 else 0)
        shown, widths = self._plan(room)
        if (room, len(self._cells), tuple(shown), tuple(sorted(widths.items()))) == self._fitted_for:
            self._show_detail()
            return
        self._fitted_for = (room, len(self._cells), tuple(shown), tuple(sorted(widths.items())))
        self._shown, self._widths = shown, widths
        picked, cursor, scroll_y = self.show_cursor, self.cursor_row, self.scroll_y
        cells = self._cells
        super().clear(columns=True)
        for i in shown:
            column = self._columns[i]
            super().add_column(column.label, width=widths[i], key=column.key)
        for row in cells:
            super().add_row(*(_fitted(row[i], widths[i]) for i in shown))
        if picked and cells:
            self.move_cursor(row=min(cursor, len(cells) - 1), scroll=False)
        self.scroll_y = scroll_y
        self._show_detail()

    # --- what the highlighted row could not show -------------------------
    def _cut(self, row: int) -> Text | None:
        parts = []
        for i, column in enumerate(self._columns):
            if not column.label or i >= len(self._cells[row]):
                continue
            value = _plain(self._cells[row][i]).strip()
            if value and (i not in self._shown or len(value) > self._widths.get(i, 0)):
                parts.append(Text.assemble((f"{column.label}: ", "bold"), value))
        return Text("  ·  ").join(parts) if parts else None

    def _show_detail(self) -> None:
        details = self.screen.query(RowDetail) if self.is_attached else []
        if details:
            row = self.picked_row
            details.first().show(self._cut(row) if row is not None and row < len(self._cells) else None)

    def watch_cursor_coordinate(self, old, new) -> None:
        super().watch_cursor_coordinate(old, new)
        self._show_detail()

    def watch_show_cursor(self, show_cursor: bool) -> None:
        super().watch_show_cursor(show_cursor)
        self._show_detail()

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


class WrapLog(VerticalScroll):
    """Lines of output, wrapped to the width the window has NOW. Textual's
    RichLog wraps a line once, at the width it had when it was written, and
    crops it after that - a window made narrower, or a scrollbar appearing,
    silently cut words out of the middle of lines. This keeps the lines and
    lays them out again on every resize. Follows the end while scrolled to
    it; scrolled up, it stays where it is."""

    DEFAULT_CSS = """
    WrapLog > Static { width: 1fr; height: auto; }
    """

    def __init__(self, *, max_lines: int | None = None, id: str | None = None) -> None:
        super().__init__(id=id)
        self.max_lines = max_lines
        self._lines: list[Text] = []
        self._pending = False

    def compose(self):
        yield Static()

    def write(self, line: Text | str) -> None:
        self._lines.append(line if isinstance(line, Text) else Text(line))
        if self.max_lines and len(self._lines) > self.max_lines:
            del self._lines[:-self.max_lines]
        if not self._pending:
            self._pending = True
            self.call_after_refresh(self._show)

    def _show(self) -> None:
        self._pending = False
        if not self.is_attached:
            return
        following = self.scroll_y >= self.max_scroll_y - 1
        self.query_one(Static).update(Text("\n").join(self._lines))
        if following:
            self.call_after_refresh(self.scroll_end, animate=False)
