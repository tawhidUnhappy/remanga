"""The terminal session the menus run in.

One alternate screen for the whole session (the way htop or lazygit work):
each screen replaces the last, nothing is left behind in the scrollback, and
quitting puts the terminal back exactly as it was. Keys come from
remanga.tui.keys, held in its raw mode for the session."""

from __future__ import annotations

from contextlib import ExitStack

from rich.console import Console, RenderableType
from rich.live import Live

from remanga.tui import keys


class Session:
    def __init__(self) -> None:
        self.console = Console()
        self._stack = ExitStack()
        self._live: Live | None = None
        self.reader = None

    def __enter__(self) -> Session:
        self.reader = self._stack.enter_context(keys.key_reader())
        self._live = self._stack.enter_context(
            Live(console=self.console, screen=True, auto_refresh=False, redirect_stdout=False,
                 redirect_stderr=False))
        return self

    def __exit__(self, *exc) -> None:
        self._stack.close()

    @property
    def size(self) -> tuple[int, int]:
        size = self.console.size
        return size.width, size.height

    def draw(self, renderable: RenderableType) -> None:
        self._live.update(renderable, refresh=True)

    def key(self) -> str:
        return self.reader.read_key()

    def key_waiting(self, timeout: float) -> bool:
        return self.reader.key_waiting(timeout)
