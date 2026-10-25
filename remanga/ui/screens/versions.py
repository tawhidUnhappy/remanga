"""A chapter's versions: every video made of it (store/versions.py), what
each was made with, the one in use marked. Enter on one brings it back
(nothing is made again) or deletes it; c checks every file of every version
against its SHA-256, so anyone can see at a glance that nothing is damaged."""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable

from remanga.store import versions as store_versions
from remanga.ui.dialogs import Choice, Confirm
from remanga.ui.widgets import KeyBar, RowDetail, SafeTable, TopBar


def _size(size: int) -> str:
    return f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"


class VersionsScreen(Screen):
    BINDINGS = [Binding("c", "check", "Check files"), Binding("escape", "back", "Back"),
                Binding("q", "app.quit", "Quit")]

    def __init__(self, project: str, chapter: str, path: list[str]) -> None:
        super().__init__()
        self.project, self.chapter = project, chapter
        self.path = [*path, f"Chapter {chapter}", "Versions"]
        self.rows: list[store_versions.Version] = []
        self.checked: dict[int, str] = {}   # version -> "ok" or what is wrong, once checked

    def compose(self) -> ComposeResult:
        yield TopBar(self.path)
        yield SafeTable(id="versions")
        yield RowDetail()
        yield KeyBar()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        for label, width, drop in (("", 9, 0), ("#", 4, 0), ("Made", 16, 2), ("Made with", None, 0),
                                   ("Size", 8, 1), ("Files", 10, 3)):
            table.add_column(label, width=width, drop=drop)
        self.load()
        table.focus()

    def load(self) -> None:
        table = self.query_one(SafeTable)
        at = table.picked_row
        table.clear()
        self.rows = list(reversed(store_versions.versions(self.project, self.chapter)))
        for v in self.rows:
            state = self.checked.get(v.id)
            files = (Text("✓ checked", style="green") if state == "ok" else Text("✗ " + state, style="bold red")
                     if state else Text("c to check", style="dim"))
            table.add_row(Text("● in use", style="bold green") if v.current else "", str(v.id), v.made,
                          v.label, Text(_size(v.size), justify="right"), files)
        total = sum(v.size for v in self.rows)
        self.query_one(TopBar).set_info(f"{len(self.rows)} version(s) · {_size(total)} kept" if self.rows
                                        else "none yet - Make video records one")
        if at is not None and self.rows:
            table.move_cursor(row=min(at, len(self.rows) - 1))

    def action_back(self) -> None:
        self.dismiss()

    @work(exclusive=True, group="check")
    async def action_check(self) -> None:
        """Every file of every version read back against its SHA-256."""
        self.notify(f"Checking every file of {len(self.rows)} version(s)...", timeout=3)
        for v in self.rows:
            self.checked[v.id] = await asyncio.to_thread(store_versions.check, self.project, v)
            self.load()
        bad = [v.id for v in self.rows if self.checked.get(v.id) != "ok"]
        self.notify("Every file of every version is exactly as it was made." if not bad else
                    f"Version(s) {', '.join(map(str, bad))} have a problem - see Files.",
                    severity="information" if not bad else "error", timeout=8)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.choose(event.cursor_row)

    @work(exclusive=True)
    async def choose(self, row: int) -> None:
        if not 0 <= row < len(self.rows):
            return
        v = self.rows[row]
        if v.current:
            self.notify(f"Version {v.id} is the one in use. To delete it, use another version first.", timeout=6)
            return
        options = [("Use this version", "put it back in the chapter's folders - its narration and video, "
                                        "from the store, nothing made again", "use"),
                   ("Delete", "remove it and every file no other version uses", "delete")]
        picked = await self.app.push_screen_wait(Choice(f"Version {v.id}", options, note=v.label,
                                                        danger=["delete"]))
        try:
            if picked == "use":
                store_versions.make_current(self.project, self.chapter, v.id)
                self.notify(f"Version {v.id} is in use. Rebuild video remakes its mix when needed.", timeout=6)
            elif picked == "delete":
                if await self.app.push_screen_wait(Confirm(
                        "Delete version", f"Delete version {v.id} ({v.label})? Its files that no other version "
                        f"uses are removed for good.", yes="Delete", danger=True)):
                    freed = store_versions.delete(self.project, self.chapter, v.id)
                    self.notify(f"Version {v.id} deleted - {_size(freed)} freed.", timeout=6)
        except Exception as error:   # a version not whole in the store, a busy chapter...
            self.notify(str(error), severity="error", timeout=10)
        self.load()
