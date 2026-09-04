"""Single-keypress terminal input - the one place remanga touches raw tty
state, so every interactive menu in the app shares exactly one
implementation of "read one key, whatever the terminal calls it".

Rich gives us rendering (`Live`) but deliberately has no key reader; without
this, every dynamic menu would have to re-open termios itself, and any one
of them restoring the terminal wrong would leave the user's shell with echo
off. Here that risk lives in one context manager (`key_reader`) that always
restores the exact attributes it found, even on an exception.

Key names are normalized strings ("up", "enter", "ctrl-a", "a", ...) rather
than raw escape bytes, so menu code never parses ANSI sequences itself and
the Windows branch below can produce identical names from a completely
different API.

Mouse input is actively neutralized rather than merely unused - see
_MOUSE_OFF and _read_escape below for exactly what a stray click or wheel
event would otherwise do to a menu.
"""

from __future__ import annotations

import codecs
import os
import sys
from contextlib import contextmanager

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

try:  # POSIX
    import select as _select
    import termios
    import tty
except ImportError:  # pragma: no cover - Windows
    _select = termios = tty = None

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


# Final byte of a CSI ("ESC [ ...") sequence -> key name, for the sequences a
# cursor key sends. Anything not listed maps to UNKNOWN and is ignored by
# callers rather than being mistaken for a printable character.
_CSI_FINAL = {"A": UP, "B": DOWN, "C": RIGHT, "D": LEFT, "H": HOME, "F": END}
# "ESC [ <n> ~" sequences (keypad/navigation cluster), keyed by <n>.
_CSI_TILDE = {"1": HOME, "3": DELETE, "4": END, "5": PAGE_UP, "6": PAGE_DOWN, "7": HOME, "8": END}
# Windows getwch() special-key second byte -> key name.
_WIN_SPECIAL = {
    "H": UP, "P": DOWN, "K": LEFT, "M": RIGHT, "G": HOME, "O": END,
    "I": PAGE_UP, "Q": PAGE_DOWN, "S": DELETE,
}

# Turn every mouse-reporting mode OFF for the lifetime of a menu, and turn
# bracketed paste ON.
#
# Both halves exist because of what a mouse does to a program reading raw
# keystrokes. Mouse reporting is a *terminal* mode, not a per-program one:
# if anything that ran earlier in this terminal (an editor, a pager, a
# previous TUI killed before it could clean up) left ?1000/?1002/?1003 on,
# then every click and every wheel notch is delivered to us as a burst of
# bytes - X10-style "ESC [ M <button> <x> <y>", where those last three are
# raw bytes carrying the cursor position, so a click at the wrong column
# sends \r (read as Enter, silently picking whatever row the cursor happened
# to be on) or \x03 (read as Ctrl+C, tearing the whole wizard down). That is
# the "clicking the scroll wheel crashes the terminal" failure exactly:
# middle-click on X11 *also* pastes the PRIMARY selection straight into
# stdin, so an arbitrary blob of text - newlines included - arrives as if
# typed, firing every Enter in it against a menu that was never shown to the
# user.
#
# So: disable the reporting modes on the way in (defensive - remanga never
# enables them), and enable bracketed paste so any paste that does arrive
# comes wrapped in ESC[200~ ... ESC[201~ and can be recognized and dropped
# whole (see _read_escape) instead of being replayed key by key.
_MOUSE_OFF = "\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1005l\x1b[?1006l\x1b[?1015l"
_PASTE_ON = "\x1b[?2004h"
_PASTE_OFF = "\x1b[?2004l"


def is_interactive() -> bool:
    """Whether a real, drivable terminal is on both ends of this process.

    False for a piped/redirected stdin (`echo 3 | remanga`), a CI log, an
    editor's non-tty "output" pane, or TERM=dumb - every menu falls back to
    plain numbered prompts in that case (see remanga.tui.fallback) instead
    of blocking forever on a keypress that can never arrive."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
    except (AttributeError, ValueError):
        return False
    if os.environ.get("TERM", "").lower() in ("dumb", ""):
        return os.name == "nt"  # Windows consoles don't set TERM at all
    return True


class _PosixReader:
    """cbreak-with-ISIG-off: keystrokes arrive one at a time, unechoed, and
    Ctrl+C arrives as the byte \\x03 instead of raising SIGINT out from
    under a half-drawn menu. Output processing (OPOST) is deliberately left
    ON - turning it off, as tty.setraw does, is what turns Rich's own
    multi-line output into a descending staircase.

    Reads go through os.read on the raw file descriptor, never
    sys.stdin.read: sys.stdin is a *buffered* reader, so asking it for one
    character of "ESC [ B" pulls all three bytes off the fd into its own
    private buffer - after which select() on the fd correctly reports
    "nothing pending" and the arrow key is misread as a bare Esc keypress
    (i.e. every Down arrow silently backs out of the menu). Owning the
    buffer here is what makes _pending() able to answer that question."""

    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._saved = None
        self._buffer = ""
        # Incremental, because a keystroke's bytes can be split across reads
        # (a multi-byte character typed into a filter) and because a mouse
        # report's coordinate bytes aren't valid UTF-8 at all - those get
        # replaced rather than raising, and are discarded by the caller.
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def __enter__(self) -> "_PosixReader":
        self._saved = termios.tcgetattr(self._fd)
        mode = termios.tcgetattr(self._fd)
        mode[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG)
        mode[6][termios.VMIN] = 1
        mode[6][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSADRAIN, mode)
        _write_control(_MOUSE_OFF + _PASTE_ON)
        return self

    def __exit__(self, *exc) -> None:
        _write_control(_PASTE_OFF)
        if self._saved is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)

    def _read(self, count: int = 1) -> str:
        """Blocks until `count` characters are available, or returns short
        on EOF (a closed stdin, which every caller treats as "give up on
        this sequence")."""
        while len(self._buffer) < count:
            try:
                chunk = os.read(self._fd, 1024)
            except (OSError, InterruptedError):
                break
            if not chunk:
                break
            self._buffer += self._decoder.decode(chunk)
        out, self._buffer = self._buffer[:count], self._buffer[count:]
        return out

    def _pending(self, timeout: float = 0.03) -> bool:
        """Whether another byte of the same escape sequence is already
        waiting. This is what tells a bare Esc keypress apart from the Esc
        that starts an arrow key: both begin with the same byte, and only
        the arrow key's remainder arrives instantly. Checks our own buffer
        first - the rest of the sequence is usually already sitting in it."""
        if self._buffer:
            return True
        try:
            ready, _, _ = _select.select([self._fd], [], [], timeout)
        except (OSError, ValueError):
            return False
        return bool(ready)

    def read_key(self) -> str:
        ch = self._read()
        if ch == "\x1b":
            return _read_escape(self._read, self._pending)
        return _translate(ch)


class _WindowsReader:  # pragma: no cover - exercised only on Windows
    """msvcrt equivalent of _PosixReader: no terminal mode to save/restore,
    and special keys arrive as a two-byte (prefix, code) pair rather than an
    ANSI escape sequence."""

    def __enter__(self) -> "_WindowsReader":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read_key(self) -> str:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return _WIN_SPECIAL.get(msvcrt.getwch(), UNKNOWN)
        return _translate(ch)


def _write_control(sequence: str) -> None:
    """Best-effort terminal control write. A terminal that ignores these
    modes simply drops them; one that can't be written to at all (a closed
    pipe on the way out) must never take the menu down with it."""
    try:
        sys.stdout.write(sequence)
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _read_escape(read, pending) -> str:
    """Consumes one complete ESC-prefixed sequence and names it.

    Every branch here consumes the sequence *in full* even when the answer
    is "ignore this", which is the whole point: a partially-consumed mouse
    report leaves its coordinate bytes in the input stream, where they are
    then read as ordinary keys - the click-becomes-Enter/Ctrl+C failure
    described at _MOUSE_OFF above. Returning UNKNOWN is how a menu says
    "nothing happened"; it never falls through to type-to-filter."""
    if not pending():
        return ESC  # a real, bare Esc keypress - nothing followed it
    second = read()
    if second not in ("[", "O"):
        return ESC  # Alt+key and friends: ignore the modifier, keep the Esc

    params = ""
    while True:
        ch = read()
        if ch == "":
            return UNKNOWN  # stdin closed mid-sequence
        if ch.isdigit() or ch == ";":
            params += ch
            continue
        if ch == "<":
            # SGR mouse report: "ESC [ < b ; x ; y (M|m)". Drain to its
            # terminator and report nothing.
            while True:
                nxt = read()
                if nxt == "" or nxt in ("M", "m"):
                    return UNKNOWN
        if ch == "M" and not params:
            # X10 mouse report: exactly three raw bytes follow, and they are
            # position data, not keystrokes. Eat them.
            read(3)
            return UNKNOWN
        if ch == "~":
            code = params.split(";")[0]
            if code in ("200", "201"):
                # Bracketed paste. ESC[200~ opens it: swallow everything up
                # to the closing ESC[201~ so a middle-click paste can't
                # replay its contents (Enter included) into this menu.
                if code == "200":
                    _swallow_paste(read)
                return UNKNOWN
            return _CSI_TILDE.get(code, UNKNOWN)
        return _CSI_FINAL.get(ch, UNKNOWN)


def _swallow_paste(read) -> None:
    """Discards pasted text up to and including its ESC[201~ terminator.
    Bounded so a pathological paste (or a terminal that never sends the
    terminator) can't spin here forever - anything past the cap is left in
    the buffer and, at worst, types into the filter."""
    seen = ""
    for _ in range(64 * 1024):
        ch = read()
        if ch == "":
            return
        seen = (seen + ch)[-6:]
        if seen.endswith("\x1b[201~"):
            return


def _translate(ch: str) -> str:
    """One printable/control character -> key name. Anything that isn't a
    recognized control byte comes back as the character itself, which is
    what makes type-to-filter work in every menu for free."""
    if ch in ("\r", "\n"):
        return ENTER
    if ch == "\t":
        return TAB
    if ch == " ":
        return SPACE
    if ch in ("\x7f", "\b", "\x08"):
        return BACKSPACE
    if ch == "\x03":
        return CTRL_C
    if ch and ord(ch) < 32:
        return f"ctrl-{chr(ord(ch) + 96)}"
    return ch


@contextmanager
def key_reader():
    """Yields an object with `.read_key() -> str` for the duration of the
    block, with the terminal restored to exactly its previous state on the
    way out - including when the block raises. Callers must check
    `is_interactive()` first; entering this on a non-tty stdin raises."""
    reader = _WindowsReader() if (os.name == "nt" and msvcrt) else _PosixReader()
    with reader:
        yield reader
