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
from remanga.ui.dialogs import Ask, Choice, Result, number_check
from remanga.ui.screens.common import _global_log
from remanga.ui.tasks import Step, TaskScreen
from remanga.ui.widgets import SafeTable, TopBar

MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac")
UPSCALE_CAPS = ((2.0, "sharpest - small panels sit noticeably small"),
                (3.0, "balanced - recommended"),
                (4.0, "fuller frame, a little softer"),
                (0.0, "no cap - every panel fills the frame, small ones look soft"))
RESOLUTIONS = ((1920, 1080, "1080p widescreen"), (2560, 1440, "1440p - keeps bigger panels sharp"),
               (3840, 2160, "4K - slowest to render"), (1280, 720, "720p widescreen"),
               (1080, 1920, "1080p vertical"), (1440, 2560, "1440p vertical"))
EDGE_FADES = ((0, "off - clips start and stop at the sample"),
              (15, "barely there - just enough to stop a click"),
              (35, "recommended"),
              (80, "softer - the end of each line eases out"),
              (150, "soft - noticeable on a line that ends abruptly"))
MUSIC_LEVELS = ((12.0, "energetic - music clearly felt"), (14.0, "balanced - recommended"),
                (18.0, "subtle - a quiet bed"))


class SettingsScreen(Screen):
    """Every setting as a row that knows how to change itself - the narrator's
    rows come from the engine (ui/voice_settings.py), the rest are here."""

    BINDINGS = [Binding("escape", "back", "Back"), Binding("q", "app.quit", "Quit")]

    def __init__(self, config: RemangaConfig, path: list[str]) -> None:
        super().__init__()
        self.config, self.path = config, path
        self.rows: list[voice_settings.Row] = []

    def compose(self) -> ComposeResult:
        scope = "this project only" if self.config.project else "defaults for every project"
        yield TopBar(self.path, scope)
        yield SafeTable(id="settings")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.add_column("Setting", width=20)
        table.add_column("Value")
        self.load()
        table.focus()

    def _rows(self) -> list[voice_settings.Row]:
        config = self.config
        audio, video, Row = config.audio, config.video, voice_settings.Row
        music = Path(audio.bgm_path).name if audio.bgm_enabled and audio.bgm_path else "off"
        return [
            *voice_settings.narrator_rows(config),
            Row("Background music", music, _change_music),
            Row("Music level", f"{audio.bgm_below_voice_lu:g} LU under the voice", _change_music_level),
            Row("Edge fade", f"{audio.edge_fade_ms} ms" if audio.edge_fade_ms else "off", _change_edge_fade),
            Row("Video size", f"{video.width}x{video.height}", _change_video_size),
            Row("Enlarge panels", f"up to {video.max_upscale:g}x" if video.max_upscale > 0 else "to fill the frame",
                _change_max_upscale),
            Row("PDF size cap", f"{config.pdf.max_mb:g} MB per file", _change_pdf_cap),
        ]

    def load(self) -> None:
        table = self.query_one(SafeTable)
        at = table.picked_row
        table.clear()
        self.rows = self._rows()
        for row in self.rows:
            table.add_row(row.label, row.value)
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


# --- the settings that belong to no engine ------------------------------------


async def _change_music(screen: SettingsScreen, config: RemangaConfig) -> None:
    folder = GLOBAL_DIR / "bgm"
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in MUSIC_EXTS) if folder.exists() else []
    current = config.audio.bgm_path if config.audio.bgm_enabled else "off"
    picked = await screen.app.push_screen_wait(Choice(
        "Background music", [("No music", "", "off")] + [(p.name, "", str(p)) for p in files],
        current=current, note=f"Put music files in {folder}/"))
    if picked == "off":
        config.audio.bgm_enabled = False
    elif picked:
        config.audio.bgm_path, config.audio.bgm_enabled = picked, True


async def _change_music_level(screen: SettingsScreen, config: RemangaConfig) -> None:
    level = await screen.app.push_screen_wait(Choice(
        "Music level", [(f"{lu:g} LU under the voice", hint, lu) for lu, hint in MUSIC_LEVELS],
        current=config.audio.bgm_below_voice_lu,
        note="Measured per track and chapter, so any music file sits at the same level."))
    if level is not None:
        config.audio.bgm_below_voice_lu = level


async def _change_edge_fade(screen: SettingsScreen, config: RemangaConfig) -> None:
    fade = await screen.app.push_screen_wait(Choice(
        "Edge fade", [(f"{ms} ms" if ms else "off", hint, ms) for ms, hint in EDGE_FADES],
        current=config.audio.edge_fade_ms,
        note="How each panel's clip starts and stops. The start is only ever faded over the silence "
             "the clip already has, so the first word is never ramped; the end may ease out through "
             "the last of the speech, which is what stops a line sounding cut off. Changing this "
             "re-mixes the chapter - it does not narrate it again."))
    if fade is not None:
        config.audio.edge_fade_ms = fade


async def _change_video_size(screen: SettingsScreen, config: RemangaConfig) -> None:
    size = await screen.app.push_screen_wait(Choice(
        "Video size", [(f"{w}x{h}", label, (w, h)) for w, h, label in RESOLUTIONS],
        current=(config.video.width, config.video.height),
        note="Panels are cut at the page's own resolution, so a bigger video keeps more of them at "
             "full detail - making a video says which panels it would shrink."))
    if size:
        config.video.width, config.video.height = size


async def _change_max_upscale(screen: SettingsScreen, config: RemangaConfig) -> None:
    cap = await screen.app.push_screen_wait(Choice(
        "Enlarge panels", [(f"up to {c:g}x" if c else "no cap", hint, c) for c, hint in UPSCALE_CAPS],
        current=config.video.max_upscale,
        note="A small panel blown up to fill a 4K frame has nothing to fill it with and looks soft. "
             "Capped, it sits smaller and stays sharp."))
    if cap is not None:
        config.video.max_upscale = cap


async def _change_pdf_cap(screen: SettingsScreen, config: RemangaConfig) -> None:
    cap = await screen.app.push_screen_wait(Ask(
        "PDF size cap", "Largest PDF file, in MB", value=f"{config.pdf.max_mb:g}",
        check=number_check(1, 2000),
        note="A chapter bigger than this is split into panels_1.pdf, panels_2.pdf, ..."))
    if cap is not None:
        config.pdf.max_mb = float(cap)
