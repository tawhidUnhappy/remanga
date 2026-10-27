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
from textual.widgets import DataTable, LoadingIndicator

from remanga import activity, workflow
from remanga.config import RemangaConfig
from remanga.store import versions as store_versions
from remanga.ui.dialogs import Ask, Choice, Confirm, Result
from remanga.ui.screens.chapter_menu import ChapterMenu
from remanga.ui.screens.chapter_work import ChapterWork
from remanga.ui.screens.common import _STATUS, _fetch_listing, _merge_rows
from remanga.ui.screens.queue import QueueScreen
from remanga.ui.screens.settings import SettingsScreen
from remanga.ui.screens.video_work import VideoWork
from remanga.ui.widgets import KeyBar, RowDetail, SafeTable, TopBar


class ChaptersScreen(ChapterMenu, VideoWork, ChapterWork, Screen):
    BINDINGS = [
        Binding("space", "pick", "Pick"),
        Binding("r", "pick_range", "Pick range"),
        Binding("p", "pick_all", "Pick all"),
        Binding("a", "download_new", "Download all new"),
        Binding("u", "update_list", "Update list"),
        Binding("o", "sources", "Sources"),
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
        yield TopBar(self.path, "fetching the chapter list…")
        yield LoadingIndicator()
        yield SafeTable(id="chapters", mark_column=True)
        yield RowDetail()
        yield KeyBar()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.display = False
        # Left out of a narrow window first to last: Ver, Next, Pages, Title (the
        # highlighted chapter's show under the table then - widgets.RowDetail).
        # Ver: how many versions of the chapter are kept (store/versions.py).
        for label, width, drop in (("", 1, 0), ("Ch", 6, 0), ("Status", 13, 0), ("Pages", 7, 2), ("Next", 24, 3),
                                   ("Ver", 3, 4), ("Title", None, 1)):
            table.add_column(label, width=width, key=label or "mark", drop=drop)
        # Each source as it does on opening: MangaDex is asked again, a site
        # read through Firefox shows its saved list.
        self.fetch(refresh=None)

    @work(exclusive=True, group="sources")
    async def action_sources(self) -> None:
        """The sites this manga comes from; a link adds the same manga on
        another one (remanga.sources) - its chapters join the list."""
        from remanga import plugins, sources

        have = [f"{i}. {source.display_name}: {entry['manga_url'] or entry['manga_id']}"
                for i, (source, entry) in enumerate(sources.project_sources(self.project), start=1)]

        def check(text: str) -> str | None:
            known = any(plugins.call(source.handles, text.strip()) for source in plugins.items("source"))
            return None if known else "A MangaDex or comix.to link to this same manga - or Esc."

        link = await self.app.push_screen_wait(Ask(
            "Sources", "Add the same manga on another site (a link)", check=check,
            note="Now: " + "; ".join(have) + ". Each chapter comes from the site that downloaded it, else the "
                 "first one with its pages - so chapters MangaDex only links to come from the next site."))
        if not link:
            return
        try:
            sources.add_source(self.project, link, self.machine)
        except Exception as error:
            await self.app.push_screen_wait(Result(self.path, "Couldn't add the source", [str(error)], ok=False))
            return
        self.query_one(TopBar).set_info("reading the new source's chapter list…")
        self.fetch(refresh=None)

    def action_update_list(self) -> None:
        """Asks the site for its chapter list now (new chapters)."""
        self.query_one(TopBar).set_info("updating the chapter list…")
        self.fetch(refresh=True)

    @work(thread=True, exclusive=True, group="fetch")
    def fetch(self, refresh: bool | None) -> None:
        if refresh or not self.offline:
            # A site read through Firefox can take minutes and wait on you
            # (a check to solve): said in the top bar as it happens.
            def say(text: str) -> None:
                self.app.call_from_thread(self.query_one(TopBar).set_info, text)

            with activity.status_to(say):
                self.listing, self.offline = _fetch_listing(self.project, self.machine, refresh)
        self.app.call_from_thread(self.load)

    def load(self) -> None:
        self.query_one(LoadingIndicator).display = False
        table = self.query_one(SafeTable)
        table.display = True
        row = table.picked_row
        table.clear()
        self.rows = _merge_rows(self.project, self.listing)
        several = len({row.get("source") for row in self.listing}) > 1
        self.marks = {m for m in self.marks if m < len(self.rows)}
        if not self.marks:
            self.anchor = None
        for index, chapter in enumerate(self.rows):
            label, style = _STATUS[chapter["status"]]
            stage = workflow.chapter_state(self.project, chapter["chapter"])
            stage = "" if stage.startswith("not downloaded") else stage.split(" - ")[-1]
            # Downloaded: its pages and how they checked out (✓ every check passed, ? not one checked download).
            checked = workflow.page_check(self.project, chapter["chapter"]) if chapter["status"] != "missing" else {}
            pages = (Text(f"{checked['count']} {checked['mark']}", justify="right",
                          style="green" if checked["mark"] == "✓" else "yellow") if checked.get("mark")
                     else Text(str(chapter.get("pages") or ""), justify="right"))
            title = Text(chapter.get("title") or "", style="dim")
            if several:  # which site each chapter comes from
                title = Text.assemble((f"{chapter.get('source') or 'local'}  ", "cyan"), title)
            if chapter.get("fallback"):  # not out in the configured language: the one it comes in
                title = Text.assemble((f"{chapter.get('language')}  ", "magenta"), title)
            kept = len(store_versions.load(self.project, chapter["chapter"])["versions"])
            table.add_row(self._mark(index), chapter["chapter"], Text(label, style=style), pages,
                          Text(stage, style="green" if stage == "video done" else ""),
                          Text(str(kept) if kept else "", justify="right", style="cyan"), title)
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
            info = "The site lists no chapters in this language" + (" (offline)" if self.offline else "")
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

    @work(exclusive=True, group="pick")
    async def action_pick_all(self) -> None:
        """Picks every chapter, or every one with its pages on disk (user
        request, 2026-10-14) - or clears the picks."""
        have = [i for i, r in enumerate(self.rows) if r["status"] in ("downloaded", "local")]
        options = [("All chapters", f"all {len(self.rows)}, downloaded or not", "all"),
                   ("All downloaded", f"the {len(have)} with their pages on disk", "downloaded")]
        if self.marks:
            options.append(("Pick none", f"clear the {len(self.marks)} picked", "none"))
        which = await self.app.push_screen_wait(Choice("Pick", options))
        if which is None:
            return
        self.marks = (set(range(len(self.rows))) if which == "all" else set(have) if which == "downloaded"
                      else set())
        self.anchor = None
        table = self.query_one(SafeTable)
        for index in range(len(self.rows)):
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
            self.notify("Every chapter the site lists is downloaded.")
            return
        if await self.app.push_screen_wait(Confirm("Download all new", f"Download {len(new)} chapter(s): "
                                                   f"{', '.join(new)}?", yes="Download")):
            await self.download(new)
            self.fetch(refresh=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        indexes = sorted(self.marks) if self.marks else [event.cursor_row]
        self.actions([self.rows[i] for i in indexes])

