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
from remanga.config.root import PROJECT_SETTINGS_KEY
from remanga.paths import GLOBAL_DIR
from remanga.paths.metadata import list_projects, load_project_metadata
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
    use_defaults,
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
        if self.config.project:
            scope = "this project only   ● = its own value, the rest follow the defaults"
        else:
            scope = "defaults for every project" + ("   ◆ = some projects set their own"
                                                    if self._overridden_elsewhere() else "")
        yield TopBar(self.path, scope)
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
        own = self._own_values()
        if config.project and own:
            rows.append(Row("Use the defaults", f"{len(own)} own value{'s' if len(own) != 1 else ''} here",
                            use_defaults, "drop this project's own values", "Project"))
        return rows

    def _own_values(self) -> dict:
        """This project's own values (project.json "settings"), when scoped to one."""
        if not self.config.project:
            return {}
        own = load_project_metadata(self.config.project).get(PROJECT_SETTINGS_KEY)
        return own if isinstance(own, dict) else {}

    def _overridden_elsewhere(self) -> dict[str, int]:
        """On the defaults screen: for each setting, how many projects set their own."""
        counts: dict[str, int] = {}
        for project in list_projects():
            own = load_project_metadata(project["name"]).get(PROJECT_SETTINGS_KEY)
            for key in own if isinstance(own, dict) else {}:
                counts[key] = counts.get(key, 0) + 1
        return counts

    def load(self) -> None:
        table = self.query_one(SafeTable)
        at = table.picked_row
        table.clear()
        self.rows = self._rows()
        # Which rows are not simply the defaults: in a project, the ones it has
        # its own value for (●); on the defaults screen, the ones some project
        # overrides (◆) - a change there does not reach that project.
        marked = set(self._own_values()) if self.config.project else set(self._overridden_elsewhere())
        mark = "● " if self.config.project else "◆ "
        shown = None
        for row in self.rows:
            # The group name once, on its first row - the list stays one flat list.
            group = row.group if row.group != shown else ""
            shown = row.group
            own = any(key == k or key.startswith(k + ".") for key in marked for k in row.keys)
            table.add_row(group, (mark if own else "  ") + row.label, row.value, row.help)
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



