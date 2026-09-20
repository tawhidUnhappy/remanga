"""The chapters screen: every chapter of a project as a table, what each one
needs next, and the menu of what can be done to it.

Doing it is screens/chapter_work.py - this file is the table, the keys and
the choices; that one is the work behind them."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, LoadingIndicator

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.ui.dialogs import Choice, Confirm
from remanga.ui.screens.chapter_work import ChapterWork
from remanga.ui.screens.common import _STATUS, _fetch_listing, _merge_rows
from remanga.ui.screens.settings import SettingsScreen
from remanga.ui.widgets import SafeTable, TopBar


class ChaptersScreen(ChapterWork, Screen):
    BINDINGS = [
        Binding("space", "pick", "Pick"),
        Binding("a", "download_new", "Download all new"),
        Binding("s", "settings", "Settings"),
        Binding("escape", "back", "Back"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, machine: RemangaConfig, project: str) -> None:
        super().__init__()
        self.machine, self.project = machine, project
        self.path = ["remanga", project]
        self.listing: list[dict] = []
        self.offline = False
        self.rows: list[dict] = []
        self.marks: set[int] = set()

    @property
    def config(self) -> RemangaConfig:
        return self.machine.for_project(self.project)

    def compose(self) -> ComposeResult:
        yield TopBar(self.path, "fetching the chapter list from MangaDex…")
        yield LoadingIndicator()
        yield SafeTable(id="chapters", mark_column=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.display = False
        for label, width in (("", 1), ("Ch", 6), ("Status", 13), ("Pages", 5), ("Next", 24), ("Title", None)):
            table.add_column(label, width=width, key=label or "mark")
        self.fetch(refresh=True)

    @work(thread=True, exclusive=True, group="fetch")
    def fetch(self, refresh: bool) -> None:
        if refresh or not self.offline:
            self.listing, self.offline = _fetch_listing(self.project, self.machine, refresh)
        self.app.call_from_thread(self.load)

    def load(self) -> None:
        self.query_one(LoadingIndicator).display = False
        table = self.query_one(SafeTable)
        table.display = True
        row = table.picked_row
        table.clear()
        self.rows = _merge_rows(self.project, self.listing)
        self.marks = {m for m in self.marks if m < len(self.rows)}
        for index, chapter in enumerate(self.rows):
            label, style = _STATUS[chapter["status"]]
            stage = workflow.chapter_state(self.project, chapter["chapter"])
            stage = "" if stage.startswith("not downloaded") else stage.split(" - ")[-1]
            table.add_row(self._mark(index), chapter["chapter"], Text(label, style=style),
                          Text(str(chapter.get("pages") or ""), justify="right"),
                          Text(stage, style="green" if stage == "video done" else ""),
                          Text(chapter.get("title") or "", style="dim"))
        if row is not None and self.rows:
            table.move_cursor(row=min(row, len(self.rows) - 1))
        table.focus()
        self.update_info()

    def _mark(self, index: int) -> Text:
        return Text("●", style="bold cyan") if index in self.marks else Text("·", style="dim")

    def update_info(self) -> None:
        have = sum(r["status"] == "downloaded" for r in self.rows)
        info = f"{len(self.rows)} chapters · {have} downloaded"
        if self.offline:
            info += " · offline"
        if self.marks:
            info += f" · {len(self.marks)} picked"
        if not self.rows:
            info = "MangaDex lists no chapters in this language" + (" (offline)" if self.offline else "")
        self.query_one(TopBar).set_info(info)

    def toggle_mark(self, index: int) -> None:
        self.marks ^= {index}
        table = self.query_one(SafeTable)
        table.update_cell_at((index, 0), self._mark(index))
        self.update_info()

    def action_pick(self) -> None:
        table = self.query_one(SafeTable)
        if table.picked_row is None:
            return
        self.toggle_mark(table.picked_row)
        table.action_cursor_down()

    def on_safe_table_mark_clicked(self, message: SafeTable.MarkClicked) -> None:
        self.toggle_mark(message.row)

    def action_back(self) -> None:
        self.dismiss()

    def action_settings(self) -> None:
        self.app.push_screen(SettingsScreen(self.machine.for_project(self.project), [*self.path, "Settings"]))

    def on_screen_resume(self) -> None:
        if self.rows:
            self.load()

    def new_chapters(self) -> list[str]:
        return [r["chapter"] for r in self.rows if r["status"] in ("missing", "partial")]

    @work(exclusive=True)
    async def action_download_new(self) -> None:
        new = self.new_chapters()
        if not new:
            self.notify("Every chapter MangaDex lists is downloaded.")
            return
        if await self.app.push_screen_wait(Confirm("Download all new", f"Download {len(new)} chapter(s): "
                                                   f"{', '.join(new)}?", yes="Download")):
            await self.download(new)
            self.fetch(refresh=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        indexes = sorted(self.marks) if self.marks else [event.cursor_row]
        self.actions([self.rows[i] for i in indexes])

    @work(exclusive=True)
    async def actions(self, chosen: list[dict]) -> None:
        project, config = self.project, self.config
        chapters = [row["chapter"] for row in chosen]
        on_disk = all(workflow.page_files(project, ch) for ch in chapters)
        some_on_disk = any(workflow.page_files(project, ch) for ch in chapters)
        title = f"Chapter {chapters[0]}" if len(chapters) == 1 else f"{len(chapters)} chapters"
        options = []
        if not on_disk:
            options.append(("Download", "fetch the pages", "download"))
        else:
            options.append(("Mark panels", "open the Panel Marker in the browser - MAGI finds them, you "
                            "fix them", "mark"))
            options += [("Make PDF", "the panels, to give to the LLM with the prompt", "pdf"),
                        ("Write narration", "type it yourself instead, panel by panel, in the browser",
                         "write"),
                        ("Review narration", "go through what the LLM wrote and flag what is wrong",
                         "review"),
                        ("Make video", "from the narration pasted into narration.json - the audio and "
                         "video already there are deleted first, so it is narrated again", "video")]
            if any(workflow.has_audio(project, ch) for ch in chapters):
                options.append(("Remake video", "the same as Make video, which already starts from "
                                "nothing", "revideo"))
                options.append(("Remake audio", "the same, but keep only the raw narration clips after - no "
                                "mix or video left on disk", "reaudio"))
            options += [("Check pages", "fix any missing or broken page", "download"),
                        ("Re-download", "delete the pages and fetch them all again", "redownload")]
        if some_on_disk:
            options += [("Reset", "delete the cut panels, PDF, narration, audio and video - the marks and "
                         "pages stay", "reset"),
                        ("Delete", "delete everything, pages included", "delete")]
        note = ", ".join(chapters) if len(chapters) > 1 else (chosen[0].get("title") or "")
        action = await self.app.push_screen_wait(Choice(title, options, note=note, danger=["reset", "delete"]))
        if action is None:
            return
        if action == "download":
            await self.download(chapters)
        elif action == "mark":
            await self.mark(chapters, config)
        elif action in ("write", "review"):
            await self.narration_pass(action, chapters, config)
        elif action == "redownload":
            if await self.app.push_screen_wait(Confirm("Re-download", f"Delete the pages of {title.lower()} and "
                                                       f"download them again?", yes="Re-download")):
                await self.download(chapters, force=True)
        elif action == "pdf":
            await self.make_pdfs(chapters, config)
        elif action == "video":
            await self.make_videos(chapters, config)
        elif action == "revideo":
            if await self.app.push_screen_wait(Confirm(
                    "Remake video", f"Narrate, mix and render {title.lower()} again from scratch? Narrating "
                    f"is the slow part, and Make video does the same thing - both delete the audio and video "
                    f"already there first.", yes="Remake")):
                await self.make_videos(chapters, config, force=True)
        elif action == "reaudio":
            if await self.app.push_screen_wait(Confirm(
                    "Remake audio", f"Narrate, mix and render {title.lower()} again from scratch to prove the "
                    f"narration is good, then delete the mix and video and keep only the raw clips? Make video "
                    f"redoes the mix and render from them later.", yes="Remake")):
                await self.make_videos(chapters, config, force=True, audio_only=True)
        elif action in ("reset", "delete"):
            what = ("everything, pages and marks included" if action == "delete"
                    else "the cut panels, PDF, pasted narration, audio and video")
            if not await self.app.push_screen_wait(Confirm(
                    action.capitalize(), f"Delete {what} for {title.lower()}? The pasted narration can't be "
                    f"recovered.", yes=action.capitalize(), danger=True)):
                return
            for chapter in chapters:
                workflow.reset_chapter(project, chapter, delete_pages=action == "delete")
        self.marks.clear()
        self.fetch(refresh=False)
