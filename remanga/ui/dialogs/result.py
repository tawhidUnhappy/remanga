"""The screens work ends on: its result, and the full log behind it."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.console import Group
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, RichLog, Static

from remanga.ui.dialogs.fit import fit_to_window
from remanga.ui.widgets import TopBar


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
