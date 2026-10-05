"""The chapters screen: every chapter of a project as a table, what each one
needs next, and the menu of what can be done to it.

Doing it is screens/chapter_work.py - this file is the table, the keys and
the choices; chapter_menu.py is the menu and chapter_work.py the work behind it."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, LoadingIndicator

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.ui.dialogs import Confirm
from remanga.ui.screens.chapter_menu import ChapterMenu
from remanga.ui.screens.chapter_work import ChapterWork
from remanga.ui.screens.common import _STATUS, _fetch_listing, _merge_rows
from remanga.ui.screens.queue import QueueScreen
from remanga.ui.screens.settings import SettingsScreen
from remanga.ui.screens.video_work import VideoWork
from remanga.ui.widgets import SafeTable, TopBar


class ChaptersScreen(ChapterMenu, VideoWork, ChapterWork, Screen):
    BINDINGS = [
        Binding("space", "pick", "Pick"),
        Binding("r", "pick_range", "Pick range"),
        Binding("a", "download_new", "Download all new"),
        Binding("j", "queue", "Queue"),
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
        self.anchor: int | None = None

    @property
    def config(self) -> RemangaConfig:
        return self.machine

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
        if not self.marks:
            self.anchor = None
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
        self.anchor = index if index in self.marks else None
        table = self.query_one(SafeTable)
        table.update_cell_at((index, 0), self._mark(index))
        self.update_info()

    def action_pick_range(self) -> None:
        """Picks every chapter from the last one picked to the highlighted one -
        chapter n to chapter m in two keys, for a long video (user request,
        2026-10-05). With nothing picked yet, it picks the highlighted row."""
        table = self.query_one(SafeTable)
        row = table.picked_row
        if row is None:
            return
        start = self.anchor if self.anchor is not None and self.anchor < len(self.rows) else row
        for index in range(min(start, row), max(start, row) + 1):
            self.marks.add(index)
            table.update_cell_at((index, 0), self._mark(index))
        self.anchor = row
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
        self.app.push_screen(SettingsScreen(self.machine, [*self.path, "Settings"]))

    def action_queue(self) -> None:
        self.app.push_screen(QueueScreen(self.machine, self.path))

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

