"""The projects screen: your manga, and starting a new one from a MangaDex
link."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.paths import list_projects, load_project_metadata
from remanga.ui.dialogs import Ask, Choice, Result
from remanga.ui.screens.chapters import ChaptersScreen
from remanga.ui.screens.common import _global_log
from remanga.ui.screens.queue import QueueScreen
from remanga.ui.screens.settings import SettingsScreen
from remanga.ui.tasks import Step, TaskOutcome, TaskScreen
from remanga.ui.widgets import KeyBar, RowDetail, SafeTable, TopBar


class ProjectsScreen(Screen):
    BINDINGS = [
        Binding("b", "brief", "Brief (LLM)"),
        Binding("n", "new", "New project"),
        Binding("d", "delete", "Delete project"),
        Binding("j", "queue", "Queue"),
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
        yield RowDetail()
        yield KeyBar()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.add_column("Project", width=40)
        table.add_column("Chapters", width=8, drop=1)
        table.add_column("Manga", drop=2)
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
                    "no projects yet - press b to describe it to an LLM, or n and paste a link")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(ChaptersScreen(self.machine, self.names[event.cursor_row]))

    def action_settings(self) -> None:
        self.app.push_screen(SettingsScreen(self.machine, ["remanga", "Settings"]))

    def action_queue(self) -> None:
        self.app.push_screen(QueueScreen(self.machine, ["remanga"]))

    @work(exclusive=True)
    async def action_delete(self) -> None:
        """The highlighted project, gone for good - after typing its name."""
        table = self.query_one(SafeTable)
        if not self.names or table.cursor_row is None or not 0 <= table.cursor_row < len(self.names):
            self.notify("Highlight the project to delete first.")
            return
        name = self.names[table.cursor_row]
        size = workflow.project_footprint(name)
        typed = await self.app.push_screen_wait(Ask(
            f"Delete {name}", f"Type {name} to delete it for good",
            check=lambda text: None if text.strip() == name else f"Type exactly {name} - or Esc to keep it.",
            note=f"Everything in it goes, and can't be brought back: {size['chapters']} chapter(s), "
                 f"{size['videos']} video(s), {size['files']} files, {size['bytes'] / 1e6:,.1f} MB - pages, panel "
                 f"marks, narration, audio and videos - and its jobs in the queue."))
        if typed is None:
            return
        try:
            workflow.delete_project(name)
        except Exception as error:
            await self.app.push_screen_wait(Result(["remanga"], "Couldn't delete it", [str(error)], ok=False))
            return
        self.notify(f"Deleted {name}.")
        self.load()

    @work(exclusive=True)
    async def action_brief(self) -> None:
        """Start from a few words: 1 write the prompt for the LLM, 2 use its reply."""
        from remanga.json_io import has_real_json_content

        path = ["remanga", "Brief"]
        reply = workflow.brief.brief_reply_path()
        replied = has_real_json_content(reply)
        options = [("1  Describe what you want → LLM", "a few words (a character, a type, a look): writes the prompt "
                    "file to give the LLM, which finds the manga, picks the chapters and designs a Drama 3 voice",
                    "prompt")]
        if replied:
            options.append(("2  Use the LLM's reply ← LLM", f"the reply pasted into {reply} is checked against "
                            "MangaDex, then the voice is saved, the project made and its chapters downloaded",
                            "reply"))
        action = await self.app.push_screen_wait(Choice(
            "Brief", options, note="" if replied else f"After the LLM answers, paste its one JSON reply into {reply} "
                                                       "and open this again."))
        if action == "prompt":
            reference = await self.app.push_screen_wait(Ask(
                "Brief", "What are you after?", note='For example: isaki, villain, yandere white hair waifu',
                check=lambda text: None if text.strip() else "Type a few words - or Esc to cancel."))
            if not reference:
                return
            try:
                prompt = workflow.make_brief_prompt(reference)
            except Exception as error:
                await self.app.push_screen_wait(Result(path, "Couldn't write the prompt", [str(error)], ok=False))
                return
            await self.app.push_screen_wait(Result(path, "Prompt ready", [
                "Give this file to the LLM (one that can open MangaDex works best):", str(prompt.resolve()), "",
                "Then paste its one JSON reply into:", str(reply.resolve()), "",
                "and press b again for step 2."], ok=True, copy=[str(prompt.resolve()), str(reply.resolve())]))
        elif action == "reply":
            outcome: TaskOutcome = await self.app.push_screen_wait(TaskScreen(path, "Using the brief reply", [
                Step("Check the manga on MangaDex, save the voice, download", lambda: workflow.apply_brief(
                    workflow.read_reply_text(None), self.machine)),
            ], _global_log()))
            if not outcome.ok:
                await self.app.push_screen_wait(Result(path, "The reply was not used", [outcome.error], ok=False,
                                                       log=_global_log()))
                return
            done = outcome.results[0]
            chapters = done.chapters
            await self.app.push_screen_wait(Result(path, f"Project {done.project}", [
                done.manga, f"Chapters {chapters[0]}-{chapters[-1]} ({len(chapters)}) downloaded.",
                f"Narrator: {done.voice.label} ({done.voice.name}, seed {done.seed}) - now the Drama 3 voice "
                f"(was {done.previous_voice}, seed {done.previous_seed}).", done.voice.cue,
                "Listen to it first with: ./run.sh voices"], ok=True, warnings=done.notes))
            self.load()
            self.app.push_screen(ChaptersScreen(self.machine, done.project))

    @work(exclusive=True)
    async def action_new(self) -> None:
        path = ["remanga", "New project"]
        source = await self.app.push_screen_wait(Ask(
            "New project", "MangaDex or comix.to link (or a title to search on MangaDex)",
            note="The project is named after the manga's title; the reading direction comes from its original "
                 "language. A comix.to link downloads through your Firefox - see the README."))
        if not source:
            return
        outcome: TaskOutcome = await self.app.push_screen_wait(TaskScreen(path, "Creating the project", [
            Step("Look the manga up", lambda: workflow.create_project(source, self.machine)),
        ], _global_log()))
        if not outcome.ok:
            await self.app.push_screen_wait(Result(path, "Couldn't create the project", [outcome.error], ok=False,
                                                   log=_global_log()))
            return
        name = outcome.results[0]
        meta = load_project_metadata(name)
        strip = meta.get("layout") == "long_strip"
        await self.app.push_screen_wait(Result(path, f"Project {name}", [
            meta.get("manga_title", ""),
            f"Reads {meta.get('reading_direction', 'right_to_left').replace('_', ' ')}"
            + (", a long strip: its chapters are cut into pages between the panels." if strip else "."),
        ], ok=True))
        self.app.push_screen(ChaptersScreen(self.machine, name))
