"""Dialogs and the screens work ends on.

Each one is dismissed with its answer, so the screens can ask in order:
`action = await app.push_screen_wait(Choice(...))`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, Label, RichLog, Static
from textual.widgets.option_list import Option

from remanga.ui.widgets import SafeOptionList, TextInput, TopBar


def _rows(widget) -> int:
    """How many rows this widget takes of its parent, margin included - none
    at all when it is hidden (the buttons, in a short window)."""
    if not widget.display:
        return 0
    return widget.outer_size.height + widget.styles.margin.height


def fit_to_window(screen: Screen, scrollable) -> None:
    """Caps the scrolling part so the whole dialog fits the window - a box
    taller than the terminal would otherwise be clipped with no way to reach
    the rest of it, which in a small window is most dialogs.

    Everything around the scrolling part is measured rather than guessed: what
    sits outside the box (the bar, the footer), the box's own border and
    padding, and its title, note or buttons. Their heights are real ones, so
    this runs after a refresh - and never measures the box itself, whose
    height is what is being decided."""
    box = scrollable.parent
    if box is None:
        return
    # In a window this short the box's own frame costs more than it is worth:
    # its border and padding alone are four of the rows there are (.cramped
    # drops them - see the CSS in ui/app.py).
    box.set_class(screen.size.height < 14, "cramped")
    outside = sum(_rows(widget) for widget in screen.children if widget is not box)
    chrome = box.gutter.height + box.styles.margin.height
    chrome += sum(_rows(child) for child in box.children if child is not scrollable)
    scrollable.styles.max_height = max(1, screen.size.height - outside - chrome)
    # The box scrolls too, as a backstop - but once its content fits again it
    # must go back to the top, or it sits one line down and hides its title,
    # and its own scrollbar has to be recomputed against the new height.
    box.scroll_home(animate=False)
    box.refresh(layout=True)


class Choice(ModalScreen[Any]):
    """A list of (label, hint, value). Dismissed with the value, or None on Esc."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, options: Sequence[tuple[str, str, Any]], *, note: str = "",
                 current: Any = None, danger: Sequence[Any] = ()) -> None:
        super().__init__()
        self.title_text, self.note = title, note
        self.values = [value for _, _, value in options]
        self.options = []
        for label, hint, value in options:
            row = Table.grid(padding=(0, 2))
            # Room for the label, plus the "◂ current" badge when there is one.
            row.add_column(width=max(len(o[0]) for o in options) + (12 if current is not None else 0))
            row.add_column(style="dim")
            name = Text(label, style="bold red" if value in danger else "bold")
            if current is not None and value == current:
                name.append("  ◂ current", style="dim")
            row.add_row(name, hint)
            self.options.append(Option(row))

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            if self.note:
                yield Static(self.note, classes="note")
            yield SafeOptionList(*self.options)
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._fit)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit)

    def _fit(self, again: bool = True) -> None:
        fit_to_window(self, self.query_one(SafeOptionList))
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


class Checklist(ModalScreen[list[Any] | None]):
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
    ]

    def __init__(self, title: str, rows: Sequence[tuple[str, str, str, Any]], *, note: str = "",
                 danger: Sequence[Any] = (), done_label: str = "Delete ticked") -> None:
        super().__init__()
        self.title_text, self.note = title, note
        self.rows, self.danger = list(rows), set(danger)
        self.ticked: set[int] = set()
        self.done_label = done_label

    def _prompt(self, index: int) -> Table:
        label, detail, hint, value = self.rows[index]
        grid = Table.grid(padding=(0, 2))
        grid.add_column(width=3)
        grid.add_column(width=max(len(r[0]) for r in self.rows))
        grid.add_column(width=max(len(r[1]) for r in self.rows), justify="right")
        grid.add_column(style="dim")
        box = Text("[x]" if index in self.ticked else "[ ]", style="bold" if index in self.ticked else "dim")
        grid.add_row(box, Text(label, style="bold red" if value in self.danger else "bold"), detail, hint)
        return grid

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self.title_text, classes="dialog-title")
            if self.note:
                yield Static(self.note, classes="note")
            yield _TickList(*[Option(self._prompt(i)) for i in range(len(self.rows))])
            yield Static("", classes="note", id="checklist-count")
        yield Footer()

    def on_mount(self) -> None:
        self._count()
        self.call_after_refresh(self._fit)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit)

    def _fit(self, again: bool = True) -> None:
        fit_to_window(self, self.query_one(SafeOptionList))
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


class Ask(ModalScreen[str | None]):
    """One line of text: typed or pasted. `check` returns an error or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, label: str, *, value: str = "", note: str = "",
                 check: Callable[[str], str | None] | None = None) -> None:
        super().__init__()
        self.title_text, self.label, self.value, self.note, self.check = title, label, value, note, check

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self.title_text, classes="dialog-title")
            yield Label(self.label)
            yield TextInput(self.value)
            # The error gets a line of its own, so the guidance stays on
            # screen exactly when it's needed - after a wrong entry.
            yield Static("", id="message", classes="note")
            if self.note:
                yield Static(self.note, classes="note")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        error = (self.check(text) if self.check else None) or ("" if text else "Type something first.")
        if error:
            message = self.query_one("#message", Static)
            message.update(Text(error, style="bold red"))
            return
        self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)


def number_check(low: float, high: float) -> Callable[[str], str | None]:
    def check(text: str) -> str | None:
        try:
            number = float(text)
        except ValueError:
            return "That isn't a number."
        return None if low <= number <= high else f"Between {low:g} and {high:g}."

    return check


class Result(Screen[None]):
    """What was made and what to do next - or what went wrong."""

    # The text is what gets focus, not a button: Enter stays the screen's
    # Continue (shown in the footer) and the arrows scroll a long result.
    AUTO_FOCUS = "#result-text"

    BINDINGS = [
        Binding("enter", "done", "Continue"),
        Binding("escape", "done", "Continue", show=False),
        Binding("l", "log", "View log"),
        Binding("c", "copy", "Copy paths"),
    ]

    def __init__(self, path: list[str], title: str, lines: Sequence[str | Text], *, ok: bool,
                 warnings: Sequence[str] = (), log: Path | None = None, copy: Sequence[str] = ()) -> None:
        super().__init__()
        self.path, self.title_text, self.lines, self.ok = path, title, lines, ok
        self.warnings, self.log_path, self.copy = warnings, log, copy

    def compose(self) -> ComposeResult:
        yield TopBar(self.path)
        body = [line if isinstance(line, Text) else Text(line) for line in self.lines]
        if self.warnings:
            body += [Text(""), *[Text(f"! {w}", style="yellow") for w in self.warnings]]
        with Vertical(classes="dialog wide " + ("ok" if self.ok else "failed")):
            yield Label(("✓ " if self.ok else "✗ ") + self.title_text, classes="dialog-title")
            with VerticalScroll(id="result-text", can_focus=True):
                yield Static(Group(*body))
            with Horizontal(classes="buttons"):
                yield Button("Continue", id="done", variant="primary")
                if self.log_path:
                    yield Button("View log", id="log")
                if self.copy:
                    yield Button("Copy paths", id="copy")
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._fit)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit)

    def _fit(self, again: bool = True) -> None:
        # Below this, the buttons cost more rows than the result itself has;
        # the same three keys are in the footer.
        self.query_one(".buttons").display = self.size.height >= 20
        fit_to_window(self, self.query_one("#result-text"))
        if again:  # the first pass measured a clipped box; settle on the second
            self.call_after_refresh(self._fit, False)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "log":
            return bool(self.log_path)
        if action == "copy":
            return bool(self.copy)
        return True

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        await self.run_action(event.button.id)

    def action_done(self) -> None:
        self.dismiss(None)

    def action_log(self) -> None:
        if self.log_path:
            self.app.push_screen(LogView(self.path, self.log_path))

    def action_copy(self) -> None:
        self.app.copy_to_clipboard("\n".join(self.copy))
        self.notify("Copied to the clipboard (if your terminal allows it - otherwise select the text with the "
                    "mouse and press Ctrl+C).", timeout=5)


class LogView(Screen[None]):
    BINDINGS = [Binding("escape,enter", "back", "Back")]

    def __init__(self, path: list[str], log: Path) -> None:
        super().__init__()
        self.path, self.log_path = path, log

    def compose(self) -> ComposeResult:
        yield TopBar([*self.path, "Log"], str(self.log_path))
        yield RichLog(wrap=True, markup=False, highlight=False, id="log")
        yield Footer()

    def on_mount(self) -> None:
        exists = self.log_path.exists()
        text = self.log_path.read_text(encoding="utf-8", errors="replace") if exists else "The log is empty."
        log = self.query_one(RichLog)
        for line in text.splitlines():
            log.write(Text(line))
        log.scroll_end(animate=False)
        log.focus()

    def action_back(self) -> None:
        self.dismiss(None)
