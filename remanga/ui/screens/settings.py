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
from remanga.paths.metadata import list_projects, load_project_metadata, save_project_metadata
from remanga.ui import voice_settings
from remanga.ui.dialogs import Ask, Choice, Confirm, Result, number_check
from remanga.ui.screens.common import _global_log
from remanga.ui.tasks import Step, TaskScreen
from remanga.ui.widgets import SafeTable, TopBar
from remanga.video.intro import INTRO_EXTS

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
PANEL_GAPS = ((0, "continuous - recommended; the trimmed margins still leave about 50 ms"),
              (120, "a beat between panels"),
              (250, "a breath between panels"),
              (350, "unhurried"),
              (600, "slow, with room to look at the panel"))
MUSIC_LEVELS = ((12.0, "energetic - music clearly felt"), (14.0, "balanced - recommended"),
                (18.0, "subtle - a quiet bed"))
# Reference points for typing a level, loudest music first.
MUSIC_LADDER = ((8.0, "loud - fights the words, hard to follow"), (12.0, "energetic - clearly felt"),
                (14.0, "balanced - recommended"), (18.0, "subtle - a quiet bed"),
                (24.0, "barely there - felt more than heard"))
# How much of a chapter the narrator reads in one go. 0 is a take per panel;
# anything else is that many minutes of narration read straight through. One
# row rather than a switch and a number, because "off" is just the shortest
# take there is.
NARRATION_TAKES = ((0.0, "one take per panel - the voice restarts at every panel"),
                   (0.5, "about 30 seconds - closest to a cloned voice, most restarts"),
                   (1.0, "about a minute - one voice all through, and still the reference's"))


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
                _change_narration_takes, "how much is read in one go",
                "Narration", ("audio.batch_narration", "audio.batch_target_minutes")),
            Row("Pause between panels",
                f"{audio.pause_between_panels_ms} ms" if audio.pause_between_panels_ms else "none (continuous)",
                _change_panel_gap, "silence between panels", "Narration",
                ("audio.pause_between_panels_ms",)),
            Row("Fade at line edges", f"{audio.edge_fade_ms} ms" if audio.edge_fade_ms else "off",
                _change_edge_fade, "softens line edges (no clicks)", "Narration",
                ("audio.edge_fade_ms",)),
            Row("Background music", Path(audio.bgm_path).name if music_on else "off", _change_music,
                f"music under the voice ({GLOBAL_DIR / 'bgm'}/)", "Sound",
                ("audio.bgm_enabled", "audio.bgm_path")),
        ]
        if music_on:  # a level for music that isn't playing would only confuse
            rows.append(Row("Music level", f"{audio.bgm_below_voice_lu:g} LU quieter than voice", _change_music_level,
                            "higher = quieter music", "Sound",
                            ("audio.bgm_below_voice_lu", "audio.bgm_custom_lu")))
        rows += [
            Row("Intro", Path(video.intro_path).name if video.intro_enabled and video.intro_path else "off",
                _change_intro, f"clip before every recap ({GLOBAL_DIR / 'intro'}/)", "Video",
                ("video.intro_enabled", "video.intro_path")),
            Row("Video size", f"{video.width}x{video.height}", _change_video_size,
                "resolution of the finished video", "Video", ("video.width", "video.height")),
            Row("Panel enlargement limit",
                f"up to {video.max_upscale:g}x" if video.max_upscale > 0 else "no limit (fill the frame)",
                _change_max_upscale, "how far small panels are blown up", "Video", ("video.max_upscale",)),
            Row("PDF file size limit", f"{config.pdf.max_mb:g} MB per file", _change_pdf_cap,
                "largest PDF part given to the LLM", "PDF", ("pdf.max_mb",)),
        ]
        own = self._own_values()
        if config.project and own:
            rows.append(Row("Use the defaults", f"{len(own)} own value{'s' if len(own) != 1 else ''} here",
                            _use_defaults, "drop this project's own values", "Project"))
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


async def _use_defaults(screen: SettingsScreen, config: RemangaConfig) -> None:
    project = config.project
    own = load_project_metadata(project).get(PROJECT_SETTINGS_KEY) or {}
    names = ", ".join(sorted(own))
    if await screen.app.push_screen_wait(Confirm(
            "Use the defaults", f"Drop this project's own values ({names}) so it follows the defaults "
            f"again? Nothing is re-rendered until you make the video.", yes="Use the defaults")):
        save_project_metadata(project, {PROJECT_SETTINGS_KEY: {}})
        # The screen saves its config after this - it must be the defaults now,
        # or the old values would be written straight back as overrides.
        screen.config = RemangaConfig.load().for_project(project)


async def _change_intro(screen: SettingsScreen, config: RemangaConfig) -> None:
    folder = GLOBAL_DIR / "intro"
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in INTRO_EXTS) if folder.exists() else []
    current = config.video.intro_path if config.video.intro_enabled else "off"
    picked = await screen.app.push_screen_wait(Choice(
        "Intro", [("No intro", "", "off")] + [(p.name, "", str(p)) for p in files],
        current=current, note=f"Played before every recap. Put intro videos in {folder}/"))
    if picked == "off":
        config.video.intro_enabled = False
    elif picked:
        config.video.intro_path, config.video.intro_enabled = picked, True


def _music_guide(current: float) -> str:
    """What a music level number means, in plain words, with the level in use marked."""
    lines = ["The number is how much QUIETER the music is than the narrator's voice,",
             "in loudness units (LU, the same scale as dB). Bigger number = quieter music.", ""]
    for lu, text in MUSIC_LADDER:
        lines.append(f"  {lu:>4g}   {text}{'   <- now' if abs(lu - current) < 1e-9 else ''}")
    if all(abs(lu - current) > 1e-9 for lu, _ in MUSIC_LADDER):
        lines.append(f"  {current:>4g}   <- now")
    lines += ["", "About 10 LU more sounds half as loud. Every song is measured, so the same",
              "number sits at the same level whichever music file is chosen."]
    return "\n".join(lines)


async def _change_music_level(screen: SettingsScreen, config: RemangaConfig) -> None:
    audio = config.audio
    options = [(f"{lu:g} LU quieter than the voice", hint, lu) for lu, hint in MUSIC_LEVELS]
    # A level typed in before is kept and offered again, beside the presets.
    custom = audio.bgm_custom_lu
    if custom is not None and all(custom != lu for lu, _ in MUSIC_LEVELS):
        options.append((f"{custom:g} LU quieter than the voice", "your custom level", custom))
    options.append(("Custom...", "type your own number - it's saved for next time", "custom"))
    level = await screen.app.push_screen_wait(Choice(
        "Music level", options, current=audio.bgm_below_voice_lu,
        note="How much quieter the music plays than the narrator. Bigger number = quieter music."))
    if level == "custom":
        typed = await screen.app.push_screen_wait(Ask(
            "Music level", "How much quieter than the voice? (a number from 3 to 30)",
            value=f"{custom if custom is not None else audio.bgm_below_voice_lu:g}",
            check=number_check(3, 30), note=_music_guide(audio.bgm_below_voice_lu)))
        if typed is None:
            return
        level = audio.bgm_custom_lu = float(typed)
    if level is not None:
        audio.bgm_below_voice_lu = level


async def _change_panel_gap(screen: SettingsScreen, config: RemangaConfig) -> None:
    gap = await screen.app.push_screen_wait(Choice(
        "Pause between panels", [(f"{ms} ms" if ms else "continuous", hint, ms) for ms, hint in PANEL_GAPS],
        current=config.audio.pause_between_panels_ms,
        note="The silence between one panel's narration and the next, and now the whole of it: the "
             "uneven lead-in the narrator leaves on each clip is trimmed back to an even margin, so "
             "this is the gap you actually hear. Changing it lays the chapter out again from the "
             "clips already on disk - nothing is narrated again, but the chapter is mixed and "
             "rendered again."))
    if gap is not None:
        config.audio.pause_between_panels_ms = gap


async def _change_edge_fade(screen: SettingsScreen, config: RemangaConfig) -> None:
    fade = await screen.app.push_screen_wait(Choice(
        "Fade at line edges", [(f"{ms} ms" if ms else "off", hint, ms) for ms, hint in EDGE_FADES],
        current=config.audio.edge_fade_ms,
        note="How each panel's clip starts and stops. The start is only ever faded over the silence "
             "the clip already has, so the first word is never ramped; the end may ease out through "
             "the last of the speech, which is what stops a line sounding cut off. Changing this "
             "re-mixes the chapter - it does not narrate it again."))
    if fade is not None:
        config.audio.edge_fade_ms = fade


async def _change_narration_takes(screen: SettingsScreen, config: RemangaConfig) -> None:
    current = config.audio.batch_target_minutes if config.audio.batch_narration else 0.0
    minutes = await screen.app.push_screen_wait(Choice(
        "Narration take length",
        [(f"about {m:g} min" if m else "one per panel", hint, m) for m, hint in NARRATION_TAKES],
        current=current,
        note="How much of the chapter the narrator reads without stopping. A panel read on its own "
             "is a performance of its own, so the tone resets at every panel - reading straight "
             "through a scene is what keeps one voice across it. Where each panel falls inside a "
             "take is found by listening to it afterwards, so the pictures are still cut to the "
             "words. Longer is not better past a point: a cloned voice holds its reference for "
             "about a minute and then drifts off it, measurably, and asked for nine minutes at "
             "once the narrator lost the thread entirely. A minute is the most that has held "
             "both the thread and the voice."))
    if minutes is not None:
        config.audio.batch_narration = minutes > 0
        if minutes > 0:
            config.audio.batch_target_minutes = minutes


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
        "Panel enlargement limit", [(f"up to {c:g}x" if c else "no cap", hint, c) for c, hint in UPSCALE_CAPS],
        current=config.video.max_upscale,
        note="A small panel blown up to fill a 4K frame has nothing to fill it with and looks soft. "
             "Capped, it sits smaller and stays sharp."))
    if cap is not None:
        config.video.max_upscale = cap


async def _change_pdf_cap(screen: SettingsScreen, config: RemangaConfig) -> None:
    cap = await screen.app.push_screen_wait(Ask(
        "PDF file size limit", "Largest PDF file, in MB", value=f"{config.pdf.max_mb:g}",
        check=number_check(1, 2000),
        note="A chapter bigger than this is split into panels_1.pdf, panels_2.pdf, ..."))
    if cap is not None:
        config.pdf.max_mb = float(cap)
