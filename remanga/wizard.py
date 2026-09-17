"""The menus (`./pipeline.sh`): pick or create a project, then download, make
the PDF, make the video - with each chapter's state shown so the next step is
obvious."""

from __future__ import annotations

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.paths import list_projects, load_project_metadata
from remanga.settings import run_settings, summary
from remanga.tui import CANCEL, Choice, ask_text, is_cancel, multiselect, select

_NEW, _SETTINGS = "__new__", "__settings__"


def run_wizard() -> None:
    console.print("[bold]remanga[/] — manga pages to recap video")
    machine = RemangaConfig.load()
    project = pick_project(machine)
    while not is_cancel(project):
        if project_menu(project, machine) == "switch":
            project = pick_project(machine)
        else:
            return


def pick_project(machine: RemangaConfig):
    while True:
        rows = []
        for p in list_projects():
            meta = load_project_metadata(p["name"])
            rows.append(Choice(p["name"], hint=f"{len(p['chapters'])} chapter(s)", detail=meta.get("manga_title", ""),
                               value=p["name"]))
        rows.append(Choice("New project…", hint="a manga from MangaDex", value=_NEW))
        rows.append(Choice("Settings", hint="for every project", value=_SETTINGS))
        picked = select("Project", rows, back_label="Quit", exit_label=None)
        if is_cancel(picked):
            return CANCEL
        if picked == _SETTINGS:
            run_settings(machine)
            continue
        if picked == _NEW:
            picked = new_project(machine)
            if is_cancel(picked):
                continue
        return picked


def new_project(machine: RemangaConfig):
    """Only asks where the manga is: the name, title and reading direction come
    from MangaDex."""
    source = ask_text("MangaDex URL (or ID, or a title to search)", allow_empty=False,
                      note="the project is named after the manga's title")
    if not source:
        return CANCEL
    try:
        return workflow.create_project(source, machine)
    except Exception as error:
        console.print(f"[bold red]Couldn't create the project:[/] {_esc(str(error))}")
        return CANCEL


def project_menu(project: str, machine: RemangaConfig) -> str:
    while True:
        config = machine.for_project(project)
        chapters = workflow.local_chapters(project)
        latest = f"{len(chapters)} chapter(s)" + (f", latest {chapters[-1]}" if chapters else "")
        picked = select(f"remanga — {project}", [
            Choice("Chapters", hint=f"{latest} · download, re-download, reset", value="download"),
            Choice("Make PDF", hint="the pages, to give to the LLM", value="pdf"),
            Choice("Make video", hint="from the pasted narration", value="video"),
            Choice("Settings", hint=f"{summary(config)['voice']} · music {summary(config)['music']}", value="settings"),
            Choice("Switch project", value="switch"),
        ], back_label="Quit", exit_label=None)
        if is_cancel(picked):
            return "quit"
        if picked == "switch":
            return "switch"
        try:
            if picked == "download":
                chapters_screen(project, config)
            elif picked == "pdf":
                _for_chapters(project, "Make the PDF for", workflow.make_pdf, config)
            elif picked == "video":
                _for_chapters(project, "Make the video for", workflow.make_video, config)
            else:
                run_settings(config)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped.[/] [dim]Run it again to carry on where it left off.[/]")
        except Exception as error:
            console.print(f"[bold red]Error:[/] {_esc(str(error))}")


def show_chapters(project: str) -> list[str]:
    chapters = workflow.local_chapters(project)
    if not chapters:
        console.print("[yellow]No chapters downloaded yet.[/]")
    for chapter in chapters:
        console.print(f"  chapter {chapter:>6}  {workflow.chapter_state(project, chapter)}")
    return chapters


def _ask_selection(label: str) -> str:
    return ask_text(label, default="", allow_empty=True,
                    note="a chapter (3), a range (1-5), several (1-5,8), or empty for all")


# --- the chapter list: download, re-download, reset ---------------------------

_ALL_NEW, _PICK = "__all_new__", "__pick__"
_STATUS_MARK = {"downloaded": "✓", "partial": "◐", "missing": "+", "local": "•"}
_STATUS_WORD = {"downloaded": "downloaded", "partial": "partly downloaded", "missing": "new",
                "local": "not on MangaDex"}


def _chapter_rows(project: str, listing: list[dict]) -> list[dict]:
    """MangaDex's chapters, plus any chapter this project has that MangaDex no
    longer lists, in reading order."""
    from remanga.chapters import chapter_key, chapter_sort_key

    rows = [dict(entry) for entry in listing]
    listed = {chapter_key(entry["chapter"]) for entry in rows}
    rows += [{"chapter": ch, "status": "local", "title": "", "pages": None}
             for ch in workflow.local_chapters(project) if chapter_key(ch) not in listed]
    return sorted(rows, key=lambda row: chapter_sort_key(row["chapter"]))


def _row_choice(project: str, row: dict, width: int) -> Choice:
    status = row["status"]
    parts = [_STATUS_WORD[status]]
    stage = workflow.chapter_state(project, row["chapter"]).split(" - ")[0]
    if status != "missing" and stage not in ("downloaded", "not downloaded"):
        parts.append(stage)
    if row.get("pages"):
        parts.append(f"{row['pages']} pages")
    if row.get("title"):
        parts.append(row["title"])
    return Choice(f"{_STATUS_MARK[status]} ch {row['chapter']:<{width}}", hint=" · ".join(parts), value=row["chapter"])


def chapters_screen(project: str, config: RemangaConfig) -> None:
    """Every chapter at once - what MangaDex has (fetched fresh on opening) and
    what is downloaded here - and everything that can be done to one: download,
    check or re-download its pages, reset it, delete it."""
    console.print("[dim]Fetching the chapter list from MangaDex...[/]")
    listing = workflow.mangadex_chapters(project, config, refresh=True)
    while True:
        rows = _chapter_rows(project, listing if listing else [])
        if not rows:
            console.print("[yellow]MangaDex lists no chapters for this manga in the configured language.[/]")
            return
        new = [r["chapter"] for r in rows if r["status"] in ("missing", "partial")]
        have = sum(r["status"] == "downloaded" for r in rows)
        width = max(len(r["chapter"]) for r in rows)
        choices = [
            Choice(f"Download all new chapters ({len(new)})",
                   hint=f"{new[0]} … {new[-1]}" if len(new) > 1 else (new[0] if new else "you have them all"),
                   value=_ALL_NEW, disabled=not new),
            Choice("Pick several…", hint="download, re-download or reset many at once", value=_PICK),
            *[_row_choice(project, row, width) for row in rows],
        ]
        picked = select(f"Chapters — {project}", choices, back_label="Back",
                        note=f"{len(rows)} chapters · {have} downloaded · ✓ downloaded  ◐ partial  + new · "
                             f"type a number to jump")
        if is_cancel(picked):
            return
        if picked == _ALL_NEW:
            workflow.download(project, new, config)
        elif picked == _PICK:
            _several(project, config, rows, width)
        else:
            _one(project, config, next(r for r in rows if r["chapter"] == picked))
        # Statuses are re-read from disk; the MangaDex list itself stays as fetched.
        listing = workflow.mangadex_chapters(project, config, refresh=False) if listing else []


def _one(project: str, config: RemangaConfig, row: dict) -> None:
    chapter, status = row["chapter"], row["status"]
    on_disk = status in ("downloaded", "partial", "local")
    actions = []
    if status in ("missing", "partial"):
        actions.append(Choice("Download", hint="fetch its pages", value="download"))
    if status in ("downloaded", "partial"):
        actions.append(Choice("Check pages", hint="fix any missing or corrupt page, keep the rest", value="check"))
        actions.append(Choice("Re-download from scratch", hint="delete its pages and fetch them all again",
                              value="redownload"))
    if on_disk:
        actions.append(Choice("Reset", hint="delete its PDF, narration, audio and video - keep the pages",
                              value="reset"))
        actions.append(Choice("Delete chapter", hint="delete everything, pages included", value="delete"))
    picked = select(f"Chapter {chapter}", actions, back_label="Back",
                    note=f"{_STATUS_WORD[status]} · {workflow.chapter_state(project, chapter)}"
                    + (f" · {row['title']}" if row.get("title") else ""))
    if not is_cancel(picked):
        _apply(project, config, picked, [chapter])


def _several(project: str, config: RemangaConfig, rows: list[dict], width: int) -> None:
    picked = multiselect("Pick chapters", [_row_choice(project, row, width) for row in rows],
                         note="space picks · type to filter · Enter when done")
    if is_cancel(picked) or not picked:
        return
    action = select(f"{len(picked)} chapter(s): what to do?", [
        Choice("Download / check pages", hint="fetch what's missing, fix what's corrupt", value="check"),
        Choice("Re-download from scratch", hint="delete their pages and fetch them all again", value="redownload"),
        Choice("Reset", hint="delete their PDF, narration, audio and video - keep the pages", value="reset"),
        Choice("Delete chapters", hint="delete everything, pages included", value="delete"),
    ], back_label="Back", note=", ".join(picked))
    if not is_cancel(action):
        _apply(project, config, action, list(picked))


def _apply(project: str, config: RemangaConfig, action: str, chapters: list[str]) -> None:
    from remanga.tui import confirm

    named = ", ".join(chapters)
    if action in ("download", "check"):
        workflow.download(project, chapters, config)
    elif action == "redownload":
        if confirm(f"Delete the pages of chapter(s) {named} and download them again?", default=False):
            workflow.download(project, chapters, config, force=True)
    elif action in ("reset", "delete"):
        what = "everything, pages included" if action == "delete" else "the PDF, pasted narration, audio and video"
        if not confirm(f"Delete {what} for chapter(s) {named}?", default=False,
                       note="the pasted narration can't be recovered - the LLM would have to write it again"):
            return
        for chapter in chapters:
            removed = workflow.reset_chapter(project, chapter, delete_pages=action == "delete")
            console.print(f"[green]✓ Chapter {chapter}:[/] " + ("deleted" if action == "delete" else "reset")
                          + f" [dim]({len(removed)} item(s) removed)[/]")


def _for_chapters(project: str, label: str, step, config: RemangaConfig) -> None:
    available = show_chapters(project)
    if not available:
        return
    chapters = workflow.select_chapters(_ask_selection(f"{label} which chapters"), available)
    for chapter in chapters:
        console.print(f"\n[bold cyan]Chapter {chapter}[/]")
        step(project, chapter, config)
