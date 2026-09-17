"""The small stateful pieces screens are built from."""

from __future__ import annotations

from dataclasses import dataclass, field

from remanga.tui import keys
from remanga.tui.key_decode import PASTE_PREFIX


@dataclass
class ListState:
    """A cursor over `count` rows, with a scroll position and marked rows.

    The cursor starts on NOTHING: no row is highlighted until an arrow key is
    pressed, so Enter pressed before looking picks nothing (user request - it
    used to be a blank row at the top)."""

    count: int = 0
    cursor: int | None = None
    top: int = 0
    marks: set[int] = field(default_factory=set)

    def resize(self, count: int) -> None:
        self.count = count
        self.marks = {m for m in self.marks if m < count}
        if self.cursor is not None and self.cursor >= count:
            self.cursor = count - 1 if count else None

    def handle(self, key: str, page: int) -> bool:
        """Moves for a navigation key; True when the key was one."""
        if not self.count:
            return key in (keys.UP, keys.DOWN, keys.PAGE_UP, keys.PAGE_DOWN, keys.HOME, keys.END)
        if key in (keys.UP, "k"):
            self.cursor = self.count - 1 if self.cursor is None else max(0, self.cursor - 1)
        elif key in (keys.DOWN, "j"):
            self.cursor = 0 if self.cursor is None else min(self.count - 1, self.cursor + 1)
        elif key == keys.PAGE_UP:
            self.cursor = max(0, (self.cursor or 0) - page)
        elif key == keys.PAGE_DOWN:
            self.cursor = min(self.count - 1, (self.cursor or 0) + page)
        elif key == keys.HOME:
            self.cursor = 0
        elif key == keys.END:
            self.cursor = self.count - 1
        else:
            return False
        return True

    def scroll_for(self, height: int) -> int:
        """Keeps the cursor inside a window of `height` rows; returns the top row."""
        visible = max(1, height)
        if self.cursor is not None:
            if self.cursor < self.top:
                self.top = self.cursor
            elif self.cursor >= self.top + visible:
                self.top = self.cursor - visible + 1
        self.top = max(0, min(self.top, max(0, self.count - visible)))
        return self.top

    def toggle_mark(self) -> None:
        if self.cursor is None:
            return
        self.marks ^= {self.cursor}

    def chosen(self) -> list[int]:
        """The marked rows, or the cursor row when nothing is marked."""
        if self.marks:
            return sorted(self.marks)
        return [self.cursor] if self.cursor is not None else []


@dataclass
class TextBox:
    value: str = ""

    def handle(self, key: str) -> bool:
        """Edits for a typing key; True when the key was one."""
        if key.startswith(PASTE_PREFIX):
            self.value += key[len(PASTE_PREFIX):]
        elif key == keys.BACKSPACE:
            self.value = self.value[:-1]
        elif key in ("ctrl-u", "ctrl-w"):
            self.value = ""
        elif key == keys.SPACE:
            self.value += " "
        elif len(key) == 1 and key.isprintable():
            self.value += key
        else:
            return False
        return True
