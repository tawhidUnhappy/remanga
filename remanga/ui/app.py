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
    width: 80; max-width: 95%; height: auto; max-height: 100%;
    border: round $accent; padding: 1 2; background: $surface;
    overflow-y: auto; scrollbar-size-vertical: 1;
}
#result-text { height: auto; overflow-x: hidden; scrollbar-size-vertical: 1; background: $surface; }
.dialog.wide { width: 96; }
/* Too short a window to spend four rows on a frame - and without one the box
   needs the full width, or the screen behind shows around it. */
.dialog.cramped, .dialog.wide.cramped { border: none; padding: 0 1; width: 100%; max-width: 100%; }
.dialog.ok { border: round $success; }
.dialog.failed { border: round $error; }
Result, Choice, Ask { align: center middle; }
.dialog-title { text-style: bold; margin-bottom: 1; }
.note { color: $text-muted; margin-bottom: 1; }
#message { margin: 1 0 0 0; }
.dialog SafeOptionList { height: auto; border: none; padding: 0; background: $surface;
                         scrollbar-size-vertical: 1; }
.dialog Input { margin-top: 1; }
.buttons { height: auto; margin-top: 1; }
.buttons Button { margin-right: 2; }

.task { height: 1fr; border: round $accent; padding: 0 2; margin: 0 1; overflow-y: auto; }
.task .dialog-title { margin: 0; }
#steps { height: auto; }
#bar-row { height: 1; }
#bar-label { width: auto; max-width: 40%; margin-right: 2; color: $text-muted;
             text-wrap: nowrap; text-overflow: ellipsis; }
#bar { width: 1fr; min-width: 8; }
#bar-detail { width: auto; color: $text-muted; margin-left: 1; text-wrap: nowrap; }
#output {
    height: 1fr; min-height: 3; margin-top: 1; border: round $panel-lighten-2; color: $text-muted;
    background: $background; overflow-x: hidden; scrollbar-size-vertical: 1;
    border-subtitle-color: $text-muted;
}

LoadingIndicator { height: 1fr; }
LogView RichLog { height: 1fr; overflow-x: hidden; }
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
