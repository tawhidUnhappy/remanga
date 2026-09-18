"""The projects screen: your manga, and starting a new one from a MangaDex
link."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.paths import list_projects, load_project_metadata
from remanga.ui.dialogs import Ask, Result
from remanga.ui.screens.chapters import ChaptersScreen
from remanga.ui.screens.common import _global_log
from remanga.ui.screens.settings import SettingsScreen
from remanga.ui.tasks import Step, TaskOutcome, TaskScreen
from remanga.ui.widgets import SafeTable, TopBar


class ProjectsScreen(Screen):
    BINDINGS = [
        Binding("n", "new", "New project"),
        Binding("s", "settings", "Settings"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, machine: RemangaConfig) -> None:
        super().__init__()
        self.machine = machine
        self.names: list[str] = []

    def compose(self) -> ComposeResult:
        yield TopBar(["remanga"])
        yield SafeTable(id="projects")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.add_column("Project", width=40)
        table.add_column("Chapters", width=8)
        table.add_column("Manga")
        self.load()
        table.focus()

    def on_screen_resume(self) -> None:
        self.load()

    def load(self) -> None:
        table = self.query_one(SafeTable)
        row = table.picked_row
        table.clear()
        projects = list_projects()
        self.names = [p["name"] for p in projects]
        for project in projects:
            meta = load_project_metadata(project["name"])
            table.add_row(project["name"], Text(str(len(project["chapters"])), justify="right"),
                          Text(meta.get("manga_title", ""), style="dim"))
        if row is not None and self.names:
            table.move_cursor(row=min(row, len(self.names) - 1))
        else:
            table.show_cursor = False
        self.query_one(TopBar).set_info(f"{len(projects)} project(s)" if projects else
                                        "no projects yet - press n and paste a MangaDex URL")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(ChaptersScreen(self.machine, self.names[event.cursor_row]))

    def action_settings(self) -> None:
        self.app.push_screen(SettingsScreen(self.machine, ["remanga", "Settings"]))

    @work(exclusive=True)
    async def action_new(self) -> None:
        path = ["remanga", "New project"]
        source = await self.app.push_screen_wait(Ask(
            "New project", "MangaDex URL (or ID, or a title to search)",
            note="The project is named after the manga's title; the reading direction comes from MangaDex."))
        if not source:
            return
        outcome: TaskOutcome = await self.app.push_screen_wait(TaskScreen(path, "Creating the project", [
            Step("Look the manga up on MangaDex", lambda: workflow.create_project(source, self.machine)),
        ], _global_log()))
        if not outcome.ok:
            await self.app.push_screen_wait(Result(path, "Couldn't create the project", [outcome.error], ok=False,
                                                   log=_global_log()))
            return
        name = outcome.results[0]
        meta = load_project_metadata(name)
        await self.app.push_screen_wait(Result(path, f"Project {name}", [
            meta.get("manga_title", ""),
            f"Reads {meta.get('reading_direction', 'right_to_left').replace('_', ' ')}.",
        ], ok=True))
        self.app.push_screen(ChaptersScreen(self.machine, name))
