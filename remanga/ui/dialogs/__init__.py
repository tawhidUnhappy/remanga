"""Dialogs and the screens work ends on.

Each one is dismissed with its answer, so the screens can ask in order:
`action = await app.push_screen_wait(Choice(...))`.

    fit.py     sizing a dialog to the window (small terminals still scroll)
    choice.py  Choice, Confirm, Checklist - pick from a list
    ask.py     Ask - a line of text, and number_check
    result.py  Result - where work ends - and LogView"""

from __future__ import annotations

from remanga.ui.dialogs.ask import Ask, number_check
from remanga.ui.dialogs.choice import Checklist, Choice, Confirm
from remanga.ui.dialogs.fit import fit_to_window
from remanga.ui.dialogs.result import LogView, Result

__all__ = ["Ask", "Checklist", "Choice", "Confirm", "LogView", "Result", "fit_to_window", "number_check"]
