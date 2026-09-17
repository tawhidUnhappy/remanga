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
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, Label, RichLog, Static
from textual.widgets.option_list import Option

from remanga.ui.widgets import SafeOptionList, TextInput, TopBar


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
            row.add_column(width=max(len(o[0]) for o in options) + (10 if current is not None else 0))
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

    def on_option_list_option_selected(self, event: SafeOptionList.OptionSelected) -> None:
        self.dismiss(self.values[event.option_index])

    def action_cancel(self) -> None:
        self.dismiss(None)


class Confirm(Choice):
    def __init__(self, title: str, message: str, *, yes: str = "Yes", danger: bool = False) -> None:
        super().__init__(title, [(yes, "", True), ("Cancel", "", False)], note=message,
                         danger=[True] if danger else [])


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
            yield Static(self.note, id="message", classes="note")
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

    AUTO_FOCUS = ""  # no button focused: Enter is the screen's Continue, shown in the footer

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
            yield Static(Group(*body))
            with Horizontal(classes="buttons"):
                yield Button("Continue", id="done", variant="primary")
                if self.log_path:
                    yield Button("View log", id="log")
                if self.copy:
                    yield Button("Copy paths", id="copy")
        yield Footer()

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
