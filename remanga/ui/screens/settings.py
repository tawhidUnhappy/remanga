"""The settings screen: every setting is a row that knows how to change
itself. The narrator's rows come from the engine (ui/voice_settings.py); the
ones defined here belong to no engine."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable

from remanga import plugins
from remanga.config import RemangaConfig
from remanga.paths import GLOBAL_DIR
from remanga.ui import look, voice_settings
from remanga.ui.dialogs import Choice, Result
from remanga.ui.screens.common import _global_log
from remanga.ui.screens.settings_sound import change_music, change_music_level, change_volume
from remanga.ui.screens.settings_video import (
    change_background_grid,
    change_intro,
    change_max_upscale,
    change_pdf_cap,
    change_video_size,
    grid_label,
)
from remanga.ui.tasks import Step, TaskScreen
from remanga.ui.widgets import KeyBar, RowDetail, SafeTable, TopBar


async def change_look(screen: SettingsScreen, config: RemangaConfig) -> None:
    picked = await screen.app.push_screen_wait(Choice(
        "Look", [(name, hint, key) for key, name, hint in look.LOOKS], current=config.menus.look,
        note="The menus' colours and shapes. Android is the web pages' look, Material 3 Expressive."))
    if picked:
        config.menus.look = picked
        look.apply(screen.app, picked)


class SettingsScreen(Screen):
    """Every setting as a row that knows how to change itself - the narrator's
    rows come from the engine (ui/voice_settings.py), the rest are here."""

    BINDINGS = [Binding("escape", "back", "Back"), Binding("q", "app.quit", "Quit")]

    def __init__(self, config: RemangaConfig, path: list[str]) -> None:
        super().__init__()
        self.config, self.path = config, path
        self.rows: list[voice_settings.Row] = []

    def compose(self) -> ComposeResult:
        yield TopBar(self.path, "applies to every project")
        yield SafeTable(id="settings")
        yield RowDetail()
        yield KeyBar()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.add_column("", width=9, drop=2)
        table.add_column("Setting", width=26)
        table.add_column("Value", width=26)
        table.add_column("What it does", drop=3)
        self.load()
        table.focus()

    def _rows(self) -> list[voice_settings.Row]:
        config = self.config
        audio, video, Row = config.audio, config.video, voice_settings.Row
        music_on = audio.bgm_enabled and bool(audio.bgm_path)
        rows = [
            *voice_settings.narrator_rows(config),
            Row("Volume", f"{audio.volume_lufs:g} LUFS", change_volume,
                "how loud the finished chapter is (YouTube is -14)", "Sound", ("audio.volume_lufs",)),
            Row("Background music", Path(audio.bgm_path).name if music_on else "off", change_music,
                f"music under the voice ({GLOBAL_DIR / 'bgm'}/)", "Sound",
                ("audio.bgm_enabled", "audio.bgm_path")),
        ]
        if music_on:  # a level for music that isn't playing would only confuse
            rows.append(Row("Music volume", f"{audio.bgm_below_voice_lu:g} LU quieter than voice", change_music_level,
                            "higher = quieter music", "Sound",
                            ("audio.bgm_below_voice_lu", "audio.bgm_custom_lu")))
        rows += [
            Row("Intro", Path(video.intro_path).name if video.intro_enabled and video.intro_path else "off",
                change_intro, f"clip before every recap ({GLOBAL_DIR / 'intro'}/)", "Video",
                ("video.intro_enabled", "video.intro_path")),
            Row("Background grid", grid_label(video.background_grid_px), change_background_grid,
                "old-phone LCD lines over the blur", "Video", ("video.background_grid_px",)),
            Row("Video size", f"{video.width}x{video.height}", change_video_size,
                "resolution of the finished video", "Video", ("video.width", "video.height")),
            Row("Panel enlargement limit",
                f"up to {video.max_upscale:g}x" if video.max_upscale > 0 else "no limit (fill the frame)",
                change_max_upscale, "how far small panels are blown up", "Video", ("video.max_upscale",)),
            Row("PDF file size limit", f"{config.pdf.max_mb:g} MB per file", change_pdf_cap,
                "largest PDF part given to the LLM", "PDF", ("pdf.max_mb",)),
            # Each manga source's own rows (sites read through Firefox: the profile, the pace, the helper).
            *(row for source in plugins.items("source") if source.settings_rows
              for row in plugins.call(source.settings_rows, config)),
            Row("Look", look.label(config.menus.look), change_look, "colours and shapes of these menus",
                "Menus", ("menus.look",)),
        ]
        return rows

    def load(self) -> None:
        table = self.query_one(SafeTable)
        at = table.picked_row
        table.clear()
        self.rows = self._rows()
        shown = None
        for row in self.rows:
            # The group name once, on its first row - the list stays one flat list.
            group = row.group if row.group != shown else ""
            shown = row.group
            table.add_row(group, row.label, row.value, row.help)
        if at is not None and self.rows:
            table.move_cursor(row=min(at, len(self.rows) - 1))

    def action_back(self) -> None:
        self.dismiss()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.change(event.cursor_row)

    async def run_work(self, title: str, step: str, work) -> bool:
        """A settings change that is real work (designing a voice downloads a
        model and runs it) - shown as a task, like any other."""
        outcome = await self.app.push_screen_wait(TaskScreen(self.path, title, [Step(step, work)], _global_log()))
        if not outcome.ok:
            await self.app.push_screen_wait(Result(self.path, title + " failed", [outcome.error], ok=False,
                                                   log=_global_log()))
        return outcome.ok

    @work(exclusive=True)
    async def change(self, row: int) -> None:
        if 0 <= row < len(self.rows):
            await self.rows[row].change(self, self.config)
            self.config.save()
            self.load()



