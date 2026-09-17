"""The full-screen menus, built on Textual.

One screen at a time, the same layout everywhere: where you are at the top,
the table or dialog in the middle, the keys at the bottom (click them too).
The mouse works throughout: the wheel scrolls, a click highlights a row, a
double click chooses it. Work runs in a task screen and ends on a result,
with the details in projects/<name>/logs/."""

from __future__ import annotations

import sys

from textual.app import App

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.ui.screens import ProjectsScreen
from remanga.ui.tasks import TaskScreen

CSS = """
.dialog {
    width: 80; max-width: 95%; height: auto; max-height: 90%;
    border: round $accent; padding: 1 2; background: $surface;
}
.dialog.wide { width: 96; }
.dialog.ok { border: round $success; }
.dialog.failed { border: round $error; }
Result, Choice, Ask { align: center middle; }
.dialog-title { text-style: bold; margin-bottom: 1; }
.note { color: $text-muted; margin-bottom: 1; }
#message { margin: 1 0 0 0; }
.dialog SafeOptionList { height: auto; max-height: 20; border: none; padding: 0; background: $surface; }
.dialog Input { margin-top: 1; }
.buttons { height: auto; margin-top: 1; }
.buttons Button { margin-right: 2; }

.task { height: 1fr; border: round $accent; padding: 1 2; margin: 1 2; }
#steps { height: auto; }
#bar-row { height: 1; margin: 1 0; }
#bar-label { width: auto; margin-right: 2; color: $text-muted; }
#bar { width: 44; }
#bar-detail { width: 1fr; color: $text-muted; margin-left: 1; }
#output { height: 1fr; border: round $panel-lighten-2; color: $text-muted; }
.task .note { margin: 1 0 0 0; }

LoadingIndicator { height: 1fr; }
LogView Log { height: 1fr; }
"""


class RemangaApp(App):
    CSS = CSS
    TITLE = "remanga"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, machine: RemangaConfig) -> None:
        super().__init__()
        self.machine = machine

    def on_mount(self) -> None:
        self.push_screen(ProjectsScreen(self.machine))

    async def action_quit(self) -> None:
        if isinstance(self.screen, TaskScreen):
            self.notify("Still working - press Ctrl+C to stop it first.", severity="warning")
            return
        self.exit()


def run() -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print("The menus need an interactive terminal. Use the commands instead - see `./run.sh --help`.")
        return
    RemangaApp(RemangaConfig.load()).run()
