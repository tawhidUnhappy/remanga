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


def is_cancel(value: Any) -> bool:
    """True when `value` is the cancellation sentinel. Use this rather than
    truthiness: a legitimately falsy answer (0, "", False, an empty
    selection) is not a cancellation."""
    return value is CANCEL
