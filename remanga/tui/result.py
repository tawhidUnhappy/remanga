"""The "the user backed out" answer, shared by every prompt in this package.

A sentinel rather than None: None is a perfectly ordinary *value* for a
menu to return (an optional command parameter left unset, "no BGM", "use
the saved manga URL"), so a caller that checked `if answer is None` would
treat those as a cancellation and abandon whatever the user was doing. The
identity check `answer is CANCEL` can't collide with any real value."""

from __future__ import annotations

from typing import Any


class _Cancel:
    """Singleton returned when a prompt is dismissed - Esc, the explicit
    Back row, or Ctrl+C where the caller has asked for it to be reported
    rather than raised."""

    _instance = None

    def __new__(cls) -> "_Cancel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "CANCEL"


CANCEL = _Cancel()


class _Exit:
    """Marker row value for "quit remanga entirely", offered on every menu.

    Distinct from CANCEL: backing out of a menu returns to whatever opened
    it, while this ends the session from wherever you are - four levels deep
    in a command's parameters included. Menus translate a selected _Exit
    into `PromptExit` immediately, so no caller ever handles this value."""

    def __repr__(self) -> str:
        return "EXIT"


EXIT = _Exit()


class PromptExit(BaseException):
    """Raised when the user asks to quit from inside any prompt - the Exit
    row, or ctrl+q.

    Deliberately a BaseException, like KeyboardInterrupt and SystemExit and
    for the same reason: it's control flow, not a failure. Every `except
    Exception` between here and cli.main() - the wizard's own "this command
    failed, back to the menu" guard included - would otherwise swallow it
    and drop the user back into the menu they just asked to leave. It
    unwinds through the raw-tty and Live context managers on the way out, so
    the terminal is already restored by the time it's caught."""


def is_cancel(value: Any) -> bool:
    """True when `value` is the cancellation sentinel. Use this rather than
    truthiness: a legitimately falsy answer (0, "", False, an empty
    selection) is not a cancellation."""
    return value is CANCEL
