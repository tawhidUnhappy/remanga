"""The settings screen: every setting is a row that knows how to change
itself. The narrator's rows come from the engine (ui/voice_settings.py); the
ones defined here belong to no engine."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer

from remanga.config import RemangaConfig
from remanga.paths import GLOBAL_DIR
from remanga.ui import voice_settings
from remanga.ui.dialogs import Result
from remanga.ui.screens.common import _global_log
from remanga.ui.screens.settings_sound import (
    change_edge_fade,
    change_music,
    change_music_level,
    change_narration_takes,
    change_panel_gap,
)
from remanga.ui.screens.settings_video import (
    change_intro,
    change_max_upscale,
    change_pdf_cap,
    change_video_size,
)
from remanga.ui.tasks import Step, TaskScreen
from remanga.ui.widgets import SafeTable, TopBar


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
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.add_column("", width=9)
        table.add_column("Setting", width=26)
        table.add_column("Value", width=26)
        table.add_column("What it does")
        self.load()
        table.focus()

    def _rows(self) -> list[voice_settings.Row]:
        config = self.config
        audio, video, Row = config.audio, config.video, voice_settings.Row
        music_on = audio.bgm_enabled and bool(audio.bgm_path)
        rows = [
            *voice_settings.narrator_rows(config),
            Row("Narration take length",
                f"about {audio.batch_target_minutes:g} min each" if audio.batch_narration else "one per panel",
                change_narration_takes, "how much is read in one go",
                "Narration", ("audio.batch_narration", "audio.batch_target_minutes")),
            Row("Pause between panels",
                f"{audio.pause_between_panels_ms} ms" if audio.pause_between_panels_ms else "none (continuous)",
                change_panel_gap, "silence between panels", "Narration",
                ("audio.pause_between_panels_ms",)),
            Row("Fade at line edges", f"{audio.edge_fade_ms} ms" if audio.edge_fade_ms else "off",
                change_edge_fade, "softens line edges (no clicks)", "Narration",
                ("audio.edge_fade_ms",)),
            Row("Background music", Path(audio.bgm_path).name if music_on else "off", change_music,
                f"music under the voice ({GLOBAL_DIR / 'bgm'}/)", "Sound",
                ("audio.bgm_enabled", "audio.bgm_path")),
        ]
        if music_on:  # a level for music that isn't playing would only confuse
            rows.append(Row("Music level", f"{audio.bgm_below_voice_lu:g} LU quieter than voice", change_music_level,
                            "higher = quieter music", "Sound",
                            ("audio.bgm_below_voice_lu", "audio.bgm_custom_lu")))
        rows += [
            Row("Intro", Path(video.intro_path).name if video.intro_enabled and video.intro_path else "off",
                change_intro, f"clip before every recap ({GLOBAL_DIR / 'intro'}/)", "Video",
                ("video.intro_enabled", "video.intro_path")),
            Row("Video size", f"{video.width}x{video.height}", change_video_size,
                "resolution of the finished video", "Video", ("video.width", "video.height")),
            Row("Panel enlargement limit",
                f"up to {video.max_upscale:g}x" if video.max_upscale > 0 else "no limit (fill the frame)",
                change_max_upscale, "how far small panels are blown up", "Video", ("video.max_upscale",)),
            Row("PDF file size limit", f"{config.pdf.max_mb:g} MB per file", change_pdf_cap,
                "largest PDF part given to the LLM", "PDF", ("pdf.max_mb",)),
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



