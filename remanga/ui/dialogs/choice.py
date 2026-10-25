"""Dialogs that pick from a list: one choice, a yes/no, or several ticked."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static
from textual.widgets.option_list import Option

from remanga.ui.dialogs.fit import fit_to_window
from remanga.ui.widgets import KeyBar, SafeOptionList

# The least room a hint gets beside its label; any narrower and it goes under
# the label instead.
MIN_HINT_WIDTH = 24


class Columns:
    """A list option's cells side by side - or, in a window too narrow for
    that, the first cells on a line and the last one (the hint) under them,
    indented. Decided each time it is drawn, at the width it is drawn at, so
    a resize relays every option out."""

    def __init__(self, cells: list[tuple[Text | str, int | None, str]], hint: Text | str) -> None:
        self.cells, self.hint = cells, hint   # cells: (content, width, justify)

    def __rich_console__(self, console, options):
        lead = sum((width or len(str(content))) + 2 for content, width, _ in self.cells)
        hint = self.hint if isinstance(self.hint, Text) else Text(self.hint, style="dim")
        grid = Table.grid(padding=(0, 2))
        for _, width, justify in self.cells:
            grid.add_column(width=width, justify=justify)
        if not hint.plain or options.max_width - lead >= MIN_HINT_WIDTH:
            grid.add_column(style="dim")
            grid.add_row(*(content for content, _, _ in self.cells), *([hint] if hint.plain else []))
            yield grid
            return
        grid.add_row(*(content for content, _, _ in self.cells))
        yield grid
        yield Padding(hint, (0, 0, 0, 2))


def note_scroller(note: str) -> VerticalScroll:
    """The explanation above a list, in a scroller of its own - fit_to_window
    gives the list its rows first and this the rest."""
    return VerticalScroll(Static(note), classes="note-scroll", can_focus=False)


class NoteScrolling:
    """Shift+Up/Down (or the mouse wheel) scroll the note while the arrows
    stay on the list. Mixed into a dialog screen that has a .note-scroll."""

    def action_note(self, rows: int) -> None:
        for note in self.query(".note-scroll"):
            note.scroll_relative(y=rows, animate=False)


class Choice(NoteScrolling, ModalScreen[Any]):
    """A list of (label, hint, value). Dismissed with the value, or None on Esc."""

    BINDINGS = [Binding("escape", "cancel", "Cancel"),
                Binding("shift+up", "note(-3)", "Scroll text", key_display="⇧↑↓"),
                Binding("shift+down", "note(3)", "Scroll text", show=False)]

    def __init__(self, title: str, options: Sequence[tuple[str, str, Any]], *, note: str = "",
                 current: Any = None, danger: Sequence[Any] = ()) -> None:
        super().__init__()
        self.title_text, self.note = title, note
        self.values = [value for _, _, value in options]
        self.options = []
        # Room for the label, plus the "◂ current" badge when there is one.
        width = max(len(o[0]) for o in options) + (12 if current is not None else 0)
        for label, hint, value in options:
            name = Text(label, style="bold red" if value in danger else "bold")
            if current is not None and value == current:
                name.append("  ◂ current", style="dim")
            self.options.append(Option(Columns([(name, width, "left")], hint)))

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            if self.note:
                yield note_scroller(self.note)
            yield SafeOptionList(*self.options)
        yield KeyBar()

    def on_mount(self) -> None:
        self.call_after_refresh(self._fit)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit)

    def _fit(self, again: bool = True) -> None:
        notes = self.query(".note-scroll")
        fit_to_window(self, self.query_one(SafeOptionList), notes.first() if notes else None)
        if again:  # the first pass measured a clipped box; settle on the second
            self.call_after_refresh(self._fit, False)

    def on_option_list_option_selected(self, event: SafeOptionList.OptionSelected) -> None:
        self.dismiss(self.values[event.option_index])

    def action_cancel(self) -> None:
        self.dismiss(None)


class Confirm(Choice):
    def __init__(self, title: str, message: str, *, yes: str = "Yes", danger: bool = False) -> None:
        super().__init__(title, [(yes, "", True), ("Cancel", "", False)], note=message,
                         danger=[True] if danger else [])


class _TickList(SafeOptionList):
    """SafeOptionList whose Enter ticks rather than chooses - and says so."""

    BINDINGS = [Binding("enter", "select", "Tick", show=False)]


class Checklist(NoteScrolling, ModalScreen[list[Any] | None]):
    """A list of (label, detail, hint, value) to tick several of. Dismissed with
    the ticked values, or None on Esc.

    Same rule as every list here: nothing is highlighted until an arrow key
    or a click, and a single click only highlights. Enter, Space or a double
    click ticks the highlighted row; `a` ticks every row (or none, if all are);
    `d` is done - the one key that moves on, so it can never be hit by
    reaching for Enter."""

    BINDINGS = [
        Binding("space", "tick", "Tick"),
        Binding("a", "tick_all", "Tick all"),
        Binding("d", "done", "Delete ticked"),
        Binding("escape", "cancel", "Cancel"),
        Binding("shift+up", "note(-3)", "Scroll text", key_display="⇧↑↓"),
        Binding("shift+down", "note(3)", "Scroll text", show=False),
    ]

    def __init__(self, title: str, rows: Sequence[tuple[str, str, str, Any]], *, note: str = "",
                 danger: Sequence[Any] = (), done_label: str = "Delete ticked") -> None:
        super().__init__()
        self.title_text, self.note = title, note
        self.rows, self.danger = list(rows), set(danger)
        self.ticked: set[int] = set()
        self.done_label = done_label

    def _prompt(self, index: int) -> Columns:
        label, detail, hint, value = self.rows[index]
        box = Text("[x]" if index in self.ticked else "[ ]", style="bold" if index in self.ticked else "dim")
        return Columns([(box, 3, "left"),
                        (Text(label, style="bold red" if value in self.danger else "bold"),
                         max(len(r[0]) for r in self.rows), "left"),
                        (detail, max(len(r[1]) for r in self.rows), "right")], hint)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self.title_text, classes="dialog-title")
            if self.note:
                yield note_scroller(self.note)
            yield _TickList(*[Option(self._prompt(i)) for i in range(len(self.rows))])
            yield Static("", classes="note", id="checklist-count")
        yield KeyBar()

    def on_mount(self) -> None:
        self._count()
        self.call_after_refresh(self._fit)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit)

    def _fit(self, again: bool = True) -> None:
        notes = self.query(".note-scroll")
        fit_to_window(self, self.query_one(SafeOptionList), notes.first() if notes else None)
        if again:
            self.call_after_refresh(self._fit, False)

    def _count(self) -> None:
        self.query_one("#checklist-count", Static).update(
            f"{len(self.ticked)} ticked - press d to {self.done_label.lower()}" if self.ticked
            else "Nothing ticked yet.")

    def _redraw(self, indexes) -> None:
        options = self.query_one(SafeOptionList)
        for index in indexes:
            options.replace_option_prompt_at_index(index, self._prompt(index))
        self._count()

    def on_option_list_option_selected(self, event: SafeOptionList.OptionSelected) -> None:
        self.ticked ^= {event.option_index}
        self._redraw([event.option_index])

    def action_tick(self) -> None:
        options = self.query_one(SafeOptionList)
        if options.highlighted is not None:
            options.action_select()

    def action_tick_all(self) -> None:
        everything = set(range(len(self.rows)))
        self.ticked = set() if self.ticked == everything else everything
        self._redraw(everything)

    def action_done(self) -> None:
        if not self.ticked:
            self.notify("Tick something first (Enter or Space on a row).")
            return
        self.dismiss([self.rows[i][3] for i in sorted(self.ticked)])

    def action_cancel(self) -> None:
        self.dismiss(None)
