"""The screens.

    Projects        your manga; n adds one from a MangaDex URL
    Chapters        a project: every chapter as a table - download, mark, PDF, video
    Settings        voice, music, video size, PDF cap

Lists open with nothing highlighted (remanga.ui.widgets). What happens after
a choice is written in order, one `await` per dialog, inside a worker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, LoadingIndicator

from remanga import activity, workflow
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.paths import GLOBAL_DIR, get_log_path, list_projects, load_project_metadata
from remanga.ui import voice_settings
from remanga.ui.dialogs import Ask, Choice, Confirm, Result, number_check
from remanga.ui.tasks import Step, TaskOutcome, TaskScreen
from remanga.ui.widgets import SafeTable, TopBar


def _short(path: Path | str) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _global_log() -> Path:
    path = Path("projects") / "remanga.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# --- projects -------------------------------------------------------------------


class ProjectsScreen(Screen):
    BINDINGS = [
        Binding("n", "new", "New project"),
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
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        table.add_column("Project", width=40)
        table.add_column("Chapters", width=8)
        table.add_column("Manga")
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
                                        "no projects yet - press n and paste a MangaDex URL")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(ChaptersScreen(self.machine, self.names[event.cursor_row]))

    def action_settings(self) -> None:
        self.app.push_screen(SettingsScreen(self.machine, ["remanga", "Settings"]))

    @work(exclusive=True)
    async def action_new(self) -> None:
        path = ["remanga", "New project"]
        source = await self.app.push_screen_wait(Ask(
            "New project", "MangaDex URL (or ID, or a title to search)",
            note="The project is named after the manga's title; the reading direction comes from MangaDex."))
        if not source:
            return
        outcome: TaskOutcome = await self.app.push_screen_wait(TaskScreen(path, "Creating the project", [
            Step("Look the manga up on MangaDex", lambda: workflow.create_project(source, self.machine)),
        ], _global_log()))
        if not outcome.ok:
            await self.app.push_screen_wait(Result(path, "Couldn't create the project", [outcome.error], ok=False,
                                                   log=_global_log()))
            return
        name = outcome.results[0]
        meta = load_project_metadata(name)
        await self.app.push_screen_wait(Result(path, f"Project {name}", [
            meta.get("manga_title", ""),
            f"Reads {meta.get('reading_direction', 'right_to_left').replace('_', ' ')}.",
        ], ok=True))
        self.app.push_screen(ChaptersScreen(self.machine, name))


# --- chapters -------------------------------------------------------------------

_STATUS = {"downloaded": ("✓ downloaded", "green"), "partial": ("◐ partial", "yellow"),
           "missing": ("+ new", "cyan"), "local": ("• local only", "dim")}


def _merge_rows(project: str, listing: list[dict]) -> list[dict]:
    from remanga.chapters import chapter_key, chapter_sort_key

    rows = [dict(entry) for entry in listing]
    listed = {chapter_key(entry["chapter"]) for entry in rows}
    rows += [{"chapter": ch, "status": "local", "title": "", "pages": None}
             for ch in workflow.local_chapters(project) if chapter_key(ch) not in listed]
    for row in rows:
        if row["status"] == "missing" and workflow.page_files(project, row["chapter"]):
            row["status"] = "partial"
    return sorted(rows, key=lambda row: chapter_sort_key(row["chapter"]))


def _fetch_listing(project: str, machine: RemangaConfig, refresh: bool) -> tuple[list[dict], bool]:
    """MangaDex's chapter list, with what it printed kept in the project log."""
    old = console.file
    activity.set_reporter(activity.Reporter())  # no progress bar drawn anywhere
    try:
        console.file = get_log_path(project).open("a", encoding="utf-8")
        return workflow.mangadex_chapters(project, machine.for_project(project), refresh=refresh), False
    except Exception:
        return [], True
    finally:
        activity.set_reporter(None)
        if console.file is not old:
            console.file.close()
        console.file = old


class ChaptersScreen(Screen):
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
                        ("Make video", "from the narration pasted into narration.json - changed settings "
                         "are picked up, finished work is reused", "video")]
            if any(workflow.has_audio(project, ch) for ch in chapters):
                options.append(("Remake video", "narrate, mix and render again from scratch, even if nothing "
                                "changed", "revideo"))
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
                    "Remake video", f"Narrate, mix and render {title.lower()} again from scratch? Narrating is "
                    f"the slow part - Make video already redoes whatever a changed setting affects.",
                    yes="Remake")):
                await self.make_videos(chapters, config, force=True)
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

    async def run_task(self, title: str, steps: list[Step], log: Path) -> TaskOutcome:
        return await self.app.push_screen_wait(TaskScreen(self.path, title, steps, log))

    async def show(self, title: str, lines: list, **kwargs: Any) -> None:
        await self.app.push_screen_wait(Result(self.path, title, lines, **kwargs))

    async def download(self, chapters: list[str], force: bool = False) -> None:
        project, config, log = self.project, self.config, get_log_path(self.project)
        outcome = await self.run_task(
            f"Downloading {len(chapters)} chapter(s)",
            [Step(f"Chapter {ch}", lambda ch=ch: workflow.download(project, [ch], config, force=force))
             for ch in chapters], log)
        if outcome.ok:
            await self.show("Downloaded", [f"Chapter(s) {', '.join(chapters)} - every page checked against "
                                           f"MangaDex."], ok=True, log=log)
        else:
            await self.show("Download stopped" if outcome.stopped else "Download failed", [outcome.error],
                            ok=False, log=log)

    async def mark(self, chapters: list[str], config: RemangaConfig) -> None:
        """The browser does the work; the task screen just waits for it."""
        project, log = self.project, get_log_path(self.project)
        outcome = await self.run_task(
            f"Marking {len(chapters)} chapter(s)",
            [Step("Panel Marker (waiting for the browser)", lambda: workflow.mark(project, chapters, config))], log)
        if outcome.ok:
            marked = [ch for ch in chapters if workflow.has_marks(project, ch)]
            await self.show("Panels marked", [f"Chapter(s) {', '.join(marked) or '-'} have their panels marked.",
                                              "", Text("Then Make PDF for the chapter.", style="dim")],
                            ok=True, log=log)
        else:
            await self.show("Marking stopped" if outcome.stopped else "Marking failed", [outcome.error],
                            ok=False, log=log)

    async def make_pdfs(self, chapters: list[str], config: RemangaConfig) -> None:
        project = self.project
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(f"Chapter {chapter}: PDF", [
                Step("Cut the panels and build their PDF",
                     lambda ch=chapter: workflow.make_pdf(project, ch, config)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: PDF {'stopped' if outcome.stopped else 'failed'}",
                                [outcome.error], ok=False, log=log)
                return
            result = outcome.results[0]
            files = [_short(result.prompt), *[_short(p) for p in result.parts]]
            lines: list[str | Text] = [
                Text("Give the LLM these files:", style="bold"), *[f"  {f}" for f in files], "",
                Text("Paste its whole reply into:", style="bold"), f"  {_short(result.narration)}", "",
                Text("Then pick the chapter and Make video.", style="dim"),
            ]
            if result.story_from:
                lines[:0] = [Text(f"Story so far carried from chapter {result.story_from}.", style="dim"), ""]
            await self.show(f"Chapter {chapter}: PDF ready", lines, ok=True, warnings=result.warnings(), log=log,
                            copy=[*files, _short(result.narration)])

    async def make_videos(self, chapters: list[str], config: RemangaConfig, force: bool = False) -> None:
        project = self.project
        for chapter in chapters:
            log = get_log_path(project, chapter)
            found: dict[str, Any] = {}

            def check(ch: str = chapter, found: dict = found) -> list:
                found["panels"], found["warnings"] = workflow.check_narration(project, ch)
                found["warnings"] += workflow.quality_warnings(project, ch, config, found["panels"])
                return found["panels"]

            outcome = await self.run_task(f"Chapter {chapter}: {'remaking the video' if force else 'video'}", [
                Step("Check the narration", check),
                Step("Narrate the panels (Kokoro)",
                     lambda ch=chapter, found=found: workflow.narrate(project, ch, found["panels"], config, force)),
                Step("Mix with the music", lambda ch=chapter: workflow.mix(project, ch, config, force)),
                Step("Render the video", lambda ch=chapter: workflow.render(project, ch, config, force)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: video {'stopped' if outcome.stopped else 'failed'}",
                                outcome.error.splitlines(), ok=False, log=log)
                return
            video = _short(outcome.results[-1])
            await self.show(f"Chapter {chapter}: video ready", [video], ok=True,
                            warnings=found.get("warnings", []), log=log, copy=[video])


# --- settings -------------------------------------------------------------------

MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac")
RESOLUTIONS = ((1920, 1080, "1080p widescreen"), (2560, 1440, "1440p - keeps bigger panels sharp"),
               (3840, 2160, "4K - slowest to render"), (1280, 720, "720p widescreen"),
               (1080, 1920, "1080p vertical"), (1440, 2560, "1440p vertical"))
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
            Row("Video size", f"{video.width}x{video.height}", _change_video_size),
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


async def _change_video_size(screen: SettingsScreen, config: RemangaConfig) -> None:
    size = await screen.app.push_screen_wait(Choice(
        "Video size", [(f"{w}x{h}", label, (w, h)) for w, h, label in RESOLUTIONS],
        current=(config.video.width, config.video.height),
        note="Panels are cut at the page's own resolution, so a bigger video keeps more of them at "
             "full detail - making a video says which panels it would shrink."))
    if size:
        config.video.width, config.video.height = size


async def _change_pdf_cap(screen: SettingsScreen, config: RemangaConfig) -> None:
    cap = await screen.app.push_screen_wait(Ask(
        "PDF size cap", "Largest PDF file, in MB", value=f"{config.pdf.max_mb:g}",
        check=number_check(1, 2000),
        note="A chapter bigger than this is split into panels_1.pdf, panels_2.pdf, ..."))
    if cap is not None:
        config.pdf.max_mb = float(cap)
