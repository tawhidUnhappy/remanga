"""A dialog that asks for a line of text, and the checks it can apply."""

from __future__ import annotations

from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, Static

from remanga.ui.widgets import TextInput


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
