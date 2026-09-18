"""The screens themselves.

    projects.py      your manga; n adds one from a MangaDex URL
    chapters.py      one project: every chapter as a table, and its menu
    chapter_work.py  what that menu does - download, mark, PDF, video
    settings.py      the settings table, engine rows included
    common.py        what more than one of them needs

Lists open with nothing highlighted (remanga/ui/widgets.py). What happens
after a choice is written in order, one `await` per dialog, inside a worker."""

from remanga.ui.screens.chapters import ChaptersScreen
from remanga.ui.screens.projects import ProjectsScreen
from remanga.ui.screens.settings import SettingsScreen

__all__ = ["ChaptersScreen", "ProjectsScreen", "SettingsScreen"]
