"""The full-screen menus (`./pipeline.sh`): one screen at a time, keys in the
footer, work shown as a task view with its details in a log file.

    term.py    the terminal session: alternate screen, keys, drawing
    views.py   what a screen looks like: frame, tables, dialogs, task view
    widgets.py small interactive pieces: a list cursor, a text box
    tasks.py   running work behind a task view, output to the chapter's log
    app.py     the screens themselves"""

from remanga.ui.app import run

__all__ = ["run"]
