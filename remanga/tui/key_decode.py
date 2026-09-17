"""A terminal's bytes -> key names: the ESC sequences a cursor key, a
navigation key, a mouse report or a bracketed paste arrive as, and single
characters. Pure functions over a read()/pending() pair, so they know
nothing about the terminal mode keys.py sets up around them."""

from __future__ import annotations

from remanga.tui.key_names import (
    BACKSPACE,
    CTRL_C,
    DELETE,
    DOWN,
    END,
    ENTER,
    ESC,
    HOME,
    LEFT,
    PAGE_DOWN,
    PAGE_UP,
    RIGHT,
    SPACE,
    TAB,
    UNKNOWN,
    UP,
)

# Final byte of a CSI ("ESC [ ...") sequence -> key name, for the sequences a
# cursor key sends. Anything not listed maps to UNKNOWN and is ignored by
# callers rather than being mistaken for a printable character.
_CSI_FINAL = {"A": UP, "B": DOWN, "C": RIGHT, "D": LEFT, "H": HOME, "F": END}
# "ESC [ <n> ~" sequences (keypad/navigation cluster), keyed by <n>.
_CSI_TILDE = {"1": HOME, "3": DELETE, "4": END, "5": PAGE_UP, "6": PAGE_DOWN, "7": HOME, "8": END}


def read_escape(read, pending, capture_paste: bool = False) -> str:
    """Consumes one complete ESC-prefixed sequence and names it.

    Every branch here consumes the sequence *in full* even when the answer
    is "ignore this", which is the whole point: a partially-consumed mouse
    report leaves its coordinate bytes in the input stream, where they are
    then read as ordinary keys - the click-becomes-Enter/Ctrl+C failure
    described at keys.py's _MOUSE_OFF. Returning UNKNOWN is how a menu says
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
                    if capture_paste:
                        return PASTE_PREFIX + read_paste(read)
                    swallow_paste(read)
                return UNKNOWN
            return _CSI_TILDE.get(code, UNKNOWN)
        return _CSI_FINAL.get(ch, UNKNOWN)


# A paste read while a text box wants one comes back as this prefix plus
# the pasted text, newlines removed.
PASTE_PREFIX = "paste:"


def read_paste(read) -> str:
    """The pasted text up to its ESC[201~ terminator, bounded like swallow_paste."""
    text = ""
    for _ in range(64 * 1024):
        ch = read()
        if ch == "":
            break
        text += ch
        if text.endswith("\x1b[201~"):
            text = text[:-6]
            break
    return text.replace("\r", "").replace("\n", "")


def swallow_paste(read) -> None:
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


def translate(ch: str) -> str:
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
