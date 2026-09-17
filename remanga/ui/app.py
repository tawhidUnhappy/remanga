"""The screens.

    Projects        your manga; n adds one from a MangaDex URL
    Chapters        a project: every chapter as a table - download, PDF, video
    Settings        voice, music, video size, PDF cap

Every list opens with nothing highlighted, so a key pressed before looking
does nothing; Esc goes back and q quits from anywhere; the footer always says
which keys do what. Work (download, PDF, video) runs in a task view and ends
on a result screen, with the details in projects/<name>/logs/."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from rich.text import Text

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.config.kokoro_voices import KOKORO_VOICES
from remanga.console import console
from remanga.paths import GLOBAL_DIR, get_log_path, list_projects, load_project_metadata
from remanga.tui import keys
from remanga.ui import views
from remanga.ui.tasks import Step, run_task
from remanga.ui.term import Session
from remanga.ui.widgets import ListState, TextBox


class Quit(Exception):
    """q pressed: leave the menus from wherever you are."""


QUIT_KEYS = ("q", "ctrl-q")
BACK_KEYS = (keys.ESC, keys.LEFT)


def run() -> None:
    if not keys.is_interactive():
        console.print("The menus need an interactive terminal. Use the commands instead - see "
                      "`./run.sh --help`.")
        return
    machine = RemangaConfig.load()
    try:
        with Session() as ui:
            projects_screen(ui, machine)
    except Quit:
        pass


# --- small interactions -------------------------------------------------------


def _read(ui: Session) -> str:
    key = ui.key()
    if key in QUIT_KEYS:
        raise Quit
    if key == keys.CTRL_C:
        raise Quit
    return key


def choose(ui: Session, path: list[str], title: str, options: Sequence[tuple[str, str, Any]], *,
           note: str = "", current: Any = None, danger: Sequence[Any] = ()) -> Any:
    """A dialog list of (label, hint, value). Returns the value, or None on Esc."""
    state = ListState(len(options))
    marked = [(label + ("  ◂ current" if value == current and current is not None else ""), hint)
              for label, hint, value in options]
    danger_rows = {i for i, (_, _, value) in enumerate(options) if value in danger}
    while True:
        _, height = ui.size
        room = max(3, views.body_height(height) - 8)
        top = state.scroll_for(room)
        shown = marked[top:top + room]
        cursor = None if state.cursor is None else state.cursor - top
        content = views.option_list(shown, cursor, danger={i - top for i in danger_rows})
        body = content if not note else views.Group(Text(note, style=views.MUTED), Text(""), content)
        ui.draw(views.frame(path, "", views.dialog(title, body, width=80),
                            [("↑↓", "move"), ("Enter", "choose"), ("Esc", "cancel"), ("q", "quit")]))
        key = _read(ui)
        if key in BACK_KEYS:
            return None
        if key == keys.ENTER and state.cursor is not None:
            return options[state.cursor][2]
        state.handle(key, room)


def ask_text(ui: Session, path: list[str], title: str, label: str, *, note: str = "", value: str = "",
             check: Callable[[str], str | None] | None = None) -> str | None:
    box, error = TextBox(value), ""
    ui.reader.capture_paste = True
    try:
        while True:
            ui.draw(views.frame(path, "", views.dialog(title, views.text_box(label, box.value, note, error), width=90),
                                [("type or paste", ""), ("Enter", "ok"), ("Esc", "cancel")]))
            key = ui.key()
            if key == keys.CTRL_C:
                raise Quit
            if key == keys.ESC:
                return None
            if key == keys.ENTER:
                text = box.value.strip()
                error = (check(text) if check else None) or ("" if text else "Type something first.")
                if not error:
                    return text
                continue
            if box.handle(key):
                error = ""
    finally:
        ui.reader.capture_paste = False


def ask_number(ui: Session, path: list[str], title: str, label: str, *, value: float, low: float,
               high: float, note: str = "") -> float | None:
    def check(text: str) -> str | None:
        try:
            number = float(text)
        except ValueError:
            return "That isn't a number."
        return None if low <= number <= high else f"Between {low:g} and {high:g}."

    answer = ask_text(ui, path, title, label, note=note, value=f"{value:g}", check=check)
    return float(answer) if answer is not None else None


def confirm(ui: Session, path: list[str], title: str, message: str, *, yes: str = "Yes", danger: bool = False) -> bool:
    answer = choose(ui, path, title, [(yes, "", True), ("Cancel", "", False)], note=message,
                    danger=[True] if danger else [])
    return answer is True


def show_result(ui: Session, path: list[str], title: str, lines: Sequence[str | Text], *, ok: bool,
                warnings: Sequence[str] = (), log: Path | None = None) -> None:
    hints = [("Enter", "continue")] + ([("l", "view log")] if log else [])
    while True:
        ui.draw(views.frame(path, "", views.result_panel(title, lines, ok=ok, warnings=warnings), hints))
        key = _read(ui)
        if key in (keys.ENTER, keys.ESC, keys.SPACE):
            return
        if key == "l" and log:
            log_screen(ui, path, log)


def log_screen(ui: Session, path: list[str], log: Path) -> None:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    top = None
    while True:
        _, height = ui.size
        room = views.body_height(height)
        if top is None:
            top = max(0, len(lines) - room)
        top = max(0, min(top, max(0, len(lines) - room)))
        text = Text("\n".join(lines[top:top + room]) or "The log is empty.", style="grey70", no_wrap=True,
                    overflow="ellipsis")
        ui.draw(views.frame([*path, "Log"], str(log), text,
                            [("↑↓ PgUp PgDn", "scroll"), ("Esc", "back"), ("q", "quit")]))
        key = _read(ui)
        if key in BACK_KEYS or key == keys.ENTER:
            return
        top += {keys.UP: -1, keys.DOWN: 1, keys.PAGE_UP: -room, keys.PAGE_DOWN: room,
                keys.HOME: -len(lines), keys.END: len(lines)}.get(key, 0)


def working(ui: Session, path: list[str], message: str) -> None:
    ui.draw(views.frame(path, "", views.centered(Text(message, style=views.MUTED)), [("…", "one moment")]))


# --- projects -------------------------------------------------------------------


def projects_screen(ui: Session, machine: RemangaConfig) -> None:
    state = ListState()
    while True:
        projects = list_projects()
        state.resize(len(projects))
        rows = []
        for project in projects:
            meta = load_project_metadata(project["name"])
            rows.append([project["name"], str(len(project["chapters"])), Text(meta.get("manga_title", ""),
                                                                              style=views.MUTED)])
        _, height = ui.size
        room = views.body_height(height)
        top = state.scroll_for(room - 1)
        body = views.table([views.Column("Project", ratio=2), views.Column("Chapters", width=8, justify="right"),
                            views.Column("Manga", ratio=3)], rows, cursor=state.cursor, top=top, height=room,
                           empty="No projects yet - press n and paste a MangaDex URL.")
        ui.draw(views.frame(["remanga"], f"{len(projects)} project(s)", body,
                            [("↑↓", "move"), ("Enter", "open"), ("n", "new project"), ("s", "settings"),
                             ("q", "quit")]))
        key = _read(ui)
        if key == keys.ENTER and state.cursor is not None:
            chapters_screen(ui, machine, projects[state.cursor]["name"])
        elif key == "n":
            name = new_project(ui, machine)
            if name:
                chapters_screen(ui, machine, name)
        elif key == "s":
            settings_screen(ui, machine, ["remanga", "Settings"])
        else:
            state.handle(key, room)


def new_project(ui: Session, machine: RemangaConfig) -> str | None:
    path = ["remanga", "New project"]
    source = ask_text(ui, path, "New project", "MangaDex URL (or ID, or a title to search)",
                      note="The project is named after the manga's title; the reading direction comes from "
                           "MangaDex.")
    if not source:
        return None
    outcome = run_task(ui, path, "Creating the project", [
        Step("Look the manga up on MangaDex", lambda: workflow.create_project(source, machine)),
    ], _global_log())
    if not outcome.ok:
        show_result(ui, path, "Couldn't create the project", [outcome.error], ok=False, log=_global_log())
        return None
    name = outcome.results[0]
    meta = load_project_metadata(name)
    show_result(ui, path, f"Project {name}", [
        meta.get("manga_title", ""),
        f"Reads {meta.get('reading_direction', 'right_to_left').replace('_', ' ')}.",
    ], ok=True)
    return name


def _global_log() -> Path:
    path = Path("projects") / "remanga.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# --- chapters -------------------------------------------------------------------

_STATUS = {"downloaded": ("✓ downloaded", views.OK), "partial": ("◐ partial", views.WARN),
           "missing": ("+ new", views.ACCENT), "local": ("• local only", views.MUTED)}


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


def chapters_screen(ui: Session, machine: RemangaConfig, project: str) -> None:
    path = ["remanga", project]
    working(ui, path, "Fetching the chapter list from MangaDex…")
    listing, offline = _fetch_listing(project, machine, refresh=True)
    state = ListState()
    while True:
        config = machine.for_project(project)
        rows = _merge_rows(project, listing)
        state.resize(len(rows))
        new = [r["chapter"] for r in rows if r["status"] in ("missing", "partial")]
        have = sum(r["status"] == "downloaded" for r in rows)
        table_rows = []
        for row in rows:
            label, style = _STATUS[row["status"]]
            stage = workflow.chapter_state(project, row["chapter"]).split(" - ")[0]
            stage = "" if stage in ("not downloaded", "downloaded") else stage
            table_rows.append([row["chapter"], Text(label, style=style), str(row.get("pages") or ""),
                               Text(stage, style=views.OK if stage == "video done" else ""),
                               Text(row.get("title") or "", style=views.MUTED)])
        _, height = ui.size
        room = views.body_height(height)
        top = state.scroll_for(room - 1)
        body = views.table([views.Column("Ch", width=6), views.Column("Status", width=13),
                            views.Column("Pages", width=5, justify="right"), views.Column("Next", width=12),
                            views.Column("Title", ratio=1)], table_rows, cursor=state.cursor, top=top,
                           height=room, marks=state.marks or None,
                           empty="MangaDex lists no chapters in this language.")
        info = f"{len(rows)} chapters · {have} downloaded" + (" · offline" if offline else "")
        picked = len(state.marks)
        hints = [("↑↓", "move"), ("Enter", "actions"), ("space", "pick"), ("a", f"download all new ({len(new)})"),
                 ("s", "settings"), ("Esc", "back"), ("q", "quit")]
        if picked:
            info += f" · {picked} picked"
        ui.draw(views.frame(path, info, body, hints))

        key = _read(ui)
        if key in BACK_KEYS:
            return
        if key == keys.SPACE:
            state.toggle_mark()
            if state.cursor is not None:
                state.handle(keys.DOWN, room)
        elif key == "a" and new:
            _download(ui, path, project, config, new)
        elif key == "s":
            settings_screen(ui, machine.for_project(project), [*path, "Settings"])
        elif key == keys.ENTER and state.chosen():
            chosen = [rows[i] for i in state.chosen()]
            if _chapter_actions(ui, path, project, config, chosen):
                state.marks.clear()
        else:
            state.handle(key, room)
            continue
        listing, offline = _fetch_listing(project, machine, refresh=False) if not offline else (listing, offline)


def _fetch_listing(project: str, machine: RemangaConfig, refresh: bool) -> tuple[list[dict], bool]:
    from remanga import activity

    old = console.file
    activity.set_reporter(activity.Reporter())  # no progress bar drawn into the log
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


def _chapter_actions(ui: Session, path: list[str], project: str, config: RemangaConfig, chosen: list[dict]) -> bool:
    chapters = [row["chapter"] for row in chosen]
    on_disk = all(workflow.page_files(project, ch) for ch in chapters)
    some_on_disk = any(workflow.page_files(project, ch) for ch in chapters)
    title = f"Chapter {chapters[0]}" if len(chapters) == 1 else f"{len(chapters)} chapters"
    options = []
    if not on_disk:
        options.append(("Download", "fetch the pages", "download"))
    else:
        options.append(("Make PDF", "the pages, to give to the LLM with the prompt", "pdf"))
        options.append(("Make video", "from the narration pasted into narration.json", "video"))
        options.append(("Check pages", "fix any missing or broken page", "download"))
        options.append(("Re-download", "delete the pages and fetch them all again", "redownload"))
    if some_on_disk:
        options.append(("Reset", "delete the PDF, narration, audio and video - keep the pages", "reset"))
        options.append(("Delete", "delete everything, pages included", "delete"))
    note = ", ".join(chapters) if len(chapters) > 1 else (chosen[0].get("title") or "")
    action = choose(ui, [*path, title], title, options, note=note, danger=["reset", "delete"])
    if action is None:
        return False
    if action == "download":
        _download(ui, path, project, config, chapters)
    elif action == "redownload":
        if confirm(ui, path, "Re-download", f"Delete the pages of {title.lower()} and download them again?"):
            _download(ui, path, project, config, chapters, force=True)
    elif action == "pdf":
        _make_pdfs(ui, path, project, config, chapters)
    elif action == "video":
        _make_videos(ui, path, project, config, chapters)
    elif action in ("reset", "delete"):
        what = "everything, pages included" if action == "delete" else "the PDF, pasted narration, audio and video"
        if confirm(ui, path, action.capitalize(), f"Delete {what} for {title.lower()}? The pasted narration can't "
                   f"be recovered.", yes=action.capitalize(), danger=True):
            for chapter in chapters:
                workflow.reset_chapter(project, chapter, delete_pages=action == "delete")
    return True


def _download(ui: Session, path: list[str], project: str, config: RemangaConfig, chapters: list[str],
              force: bool = False) -> None:
    log = get_log_path(project)
    steps = [Step(f"Chapter {ch}", (lambda ch=ch: workflow.download(project, [ch], config, force=force)))
             for ch in chapters]
    outcome = run_task(ui, path, f"Downloading {len(chapters)} chapter(s)", steps, log)
    if outcome.ok:
        show_result(ui, path, "Downloaded", [f"Chapter(s) {', '.join(chapters)} - every page checked against "
                                             f"MangaDex."], ok=True, log=log)
    else:
        show_result(ui, path, "Download stopped" if outcome.stopped else "Download failed", [outcome.error],
                    ok=False, log=log)


def _make_pdfs(ui: Session, path: list[str], project: str, config: RemangaConfig, chapters: list[str]) -> None:
    for chapter in chapters:
        log = get_log_path(project, chapter)
        outcome = run_task(ui, path, f"Chapter {chapter}: PDF", [
            Step("Build the PDF of the pages", lambda ch=chapter: workflow.make_pdf(project, ch, config)),
        ], log)
        if not outcome.ok:
            show_result(ui, path, f"Chapter {chapter}: PDF failed", [outcome.error], ok=False, log=log)
            return
        result = outcome.results[0]
        lines: list[str | Text] = [
            Text("Give the LLM these files:", style="bold"),
            f"  {_short(result.prompt)}", *[f"  {_short(p)}" for p in result.parts], "",
            Text("Paste its whole reply into:", style="bold"), f"  {_short(result.narration)}", "",
            Text("Then pick the chapter and Make video.", style=views.MUTED),
        ]
        if result.story_from:
            lines.insert(0, Text(f"Story so far carried from chapter {result.story_from}.", style=views.MUTED))
        show_result(ui, path, f"Chapter {chapter}: PDF ready", lines, ok=True, warnings=result.warnings(), log=log)


def _make_videos(ui: Session, path: list[str], project: str, config: RemangaConfig, chapters: list[str]) -> None:
    for chapter in chapters:
        if not _make_video(ui, path, project, config, chapter):
            return


def _make_video(ui: Session, path: list[str], project: str, config: RemangaConfig, chapter: str) -> bool:
    log = get_log_path(project, chapter)
    found: dict[str, Any] = {}

    def check() -> list:
        found["pages"], found["warnings"] = workflow.check_narration(project, chapter)
        return found["pages"]

    outcome = run_task(ui, path, f"Chapter {chapter}: video", [
        Step("Check the narration", check),
        Step("Narrate the pages (Kokoro)", lambda: workflow.narrate(project, chapter, found["pages"], config)),
        Step("Mix with the music", lambda: workflow.mix(project, chapter, config)),
        Step("Render the video", lambda: workflow.render(project, chapter, config)),
    ], log)
    if not outcome.ok:
        show_result(ui, path, f"Chapter {chapter}: video {'stopped' if outcome.stopped else 'failed'}",
                    outcome.error.splitlines(), ok=False, log=log)
        return False
    show_result(ui, path, f"Chapter {chapter}: video ready", [_short(outcome.results[-1])], ok=True,
                warnings=found.get("warnings", []), log=log)
    return True


def _short(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


# --- settings -------------------------------------------------------------------

MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac")
RESOLUTIONS = ((1920, 1080, "1080p widescreen"), (1280, 720, "720p widescreen"), (1080, 1920, "1080p vertical"))
MUSIC_LEVELS = ((12.0, "energetic - music clearly felt"), (14.0, "balanced - recommended"),
                (18.0, "subtle - a quiet bed"))


def settings_screen(ui: Session, config: RemangaConfig, path: list[str]) -> None:
    state = ListState()
    scope = f"saved for {config.project}" if config.project else "saved for every project"
    while True:
        audio = config.audio
        music = Path(audio.bgm_path).name if audio.bgm_enabled and audio.bgm_path else "off"
        rows = [
            ["Narrator voice", config.tts.voice_label],
            ["Speaking speed", f"{config.tts.speed:g}x"],
            ["Background music", music],
            ["Music level", f"{audio.bgm_below_voice_lu:g} LU under the voice"],
            ["Video size", f"{config.video.width}x{config.video.height}"],
            ["PDF size cap", f"{config.pdf.max_mb:g} MB per file"],
        ]
        state.resize(len(rows))
        _, height = ui.size
        body = views.table([views.Column("Setting", width=20), views.Column("Value", ratio=1)], rows,
                           cursor=state.cursor, top=0, height=views.body_height(height))
        ui.draw(views.frame(path, scope, body, [("↑↓", "move"), ("Enter", "change"), ("Esc", "back"),
                                                ("q", "quit")]))
        key = _read(ui)
        if key in BACK_KEYS:
            return
        if key != keys.ENTER or state.cursor is None:
            state.handle(key, len(rows))
            continue
        _change_setting(ui, config, path, state.cursor)
        config.save()


def _change_setting(ui: Session, config: RemangaConfig, path: list[str], row: int) -> None:
    if row == 0:
        voice = choose(ui, path, "Narrator voice", [(v.label, f"grade {v.grade} · {v.accent}", v.name)
                                                    for v in KOKORO_VOICES], current=config.tts.voice,
                       note="Kokoro-82M's voices, best graded first. A new voice narrates chapters again.")
        if voice:
            config.tts.voice = voice
    elif row == 1:
        speed = ask_number(ui, path, "Speaking speed", "Speed (1.0 is normal)", value=config.tts.speed, low=0.5,
                           high=2.0, note="1.33 is about 237 words a minute; past about 1.35 Kokoro starts "
                                          "dropping the pauses between sentences.")
        if speed is not None:
            config.tts.speed = speed
    elif row == 2:
        folder = GLOBAL_DIR / "bgm"
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in MUSIC_EXTS) if folder.exists() else []
        current = config.audio.bgm_path if config.audio.bgm_enabled else "off"
        picked = choose(ui, path, "Background music", [("No music", "", "off")] +
                        [(p.name, "", str(p)) for p in files], current=current,
                        note=f"Put music files in {folder}/")
        if picked == "off":
            config.audio.bgm_enabled = False
        elif picked:
            config.audio.bgm_path, config.audio.bgm_enabled = picked, True
    elif row == 3:
        level = choose(ui, path, "Music level", [(f"{lu:g} LU under the voice", hint, lu) for lu, hint in MUSIC_LEVELS],
                       current=config.audio.bgm_below_voice_lu,
                       note="Measured per track and chapter, so any music file sits at the same level.")
        if level is not None:
            config.audio.bgm_below_voice_lu = level
    elif row == 4:
        size = choose(ui, path, "Video size", [(f"{w}x{h}", label, (w, h)) for w, h, label in RESOLUTIONS],
                      current=(config.video.width, config.video.height))
        if size:
            config.video.width, config.video.height = size
    elif row == 5:
        cap = ask_number(ui, path, "PDF size cap", "Largest PDF file, in MB", value=config.pdf.max_mb, low=1,
                         high=2000, note="A chapter bigger than this is split into pages_1.pdf, pages_2.pdf, ...")
        if cap is not None:
            config.pdf.max_mb = cap
