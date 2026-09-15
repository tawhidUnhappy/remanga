"""The names keys are read as - "up", "enter", "ctrl-c", or the character
itself - so menu code never parses escape bytes. keys.py's readers produce
them, key_decode.py maps a terminal's bytes to them, and keys.py re-exports
every one."""

from __future__ import annotations

UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"
ENTER = "enter"
SPACE = "space"
TAB = "tab"
ESC = "esc"
BACKSPACE = "backspace"
DELETE = "delete"
HOME = "home"
END = "end"
PAGE_UP = "pgup"
PAGE_DOWN = "pgdn"
CTRL_C = "ctrl-c"
UNKNOWN = "unknown"
