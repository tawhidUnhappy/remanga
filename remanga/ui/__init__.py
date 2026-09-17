"""The full-screen menus (`./pipeline.sh`), built on Textual.

    app.py      the app: styles, quitting, entry point
    screens.py  projects, chapters (download / PDF / video), settings
    dialogs.py  choices, text questions, results, the log viewer
    tasks.py    running work in a task screen, output to the chapter's log
    widgets.py  the top bar, and a table and option list that start with
                nothing highlighted and choose on double click only"""

from remanga.ui.app import run

__all__ = ["run"]
