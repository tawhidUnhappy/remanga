"""The menus (`./pipeline.sh`): pick or create a project, then download, make
the PDF, make the video - with each chapter's state shown so the next step is
obvious."""

from __future__ import annotations

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.paths import list_projects, load_project_metadata, save_project_metadata
from remanga.settings import run_settings, summary
from remanga.tui import CANCEL, Choice, ask_text, is_cancel, select

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
            picked = new_project()
            if is_cancel(picked):
                continue
        return picked


def new_project():
    existing = {p["name"].casefold() for p in list_projects()}

    def valid_name(raw: str) -> str | None:
        if any(ch in raw for ch in "/\\"):
            return "A project name can't contain / or \\."
        return f"'{raw}' already exists." if raw.casefold() in existing else None

    name = ask_text("Project name", allow_empty=False, validate=valid_name, note="becomes projects/<name>/")
    if not name:
        return CANCEL
    source = ask_text("MangaDex URL, ID or title", allow_empty=False)
    if not source:
        return CANCEL
    save_project_metadata(name, {"project_name": name, "manga_url": source.strip()})
    return name


def project_menu(project: str, machine: RemangaConfig) -> str:
    while True:
        config = machine.for_project(project)
        chapters = workflow.local_chapters(project)
        latest = f"{len(chapters)} chapter(s)" + (f", latest {chapters[-1]}" if chapters else "")
        picked = select(f"remanga — {project}", [
            Choice("Download chapters", hint=latest, value="download"),
            Choice("Make PDF", hint="the pages, to give to the LLM", value="pdf"),
            Choice("Make video", hint="from the pasted narration", value="video"),
            Choice("Chapters", hint="where each chapter is", value="list"),
            Choice("Settings", hint=f"{summary(config)['voice']} · music {summary(config)['music']}", value="settings"),
            Choice("Switch project", value="switch"),
        ], back_label="Quit", exit_label=None)
        if is_cancel(picked):
            return "quit"
        if picked == "switch":
            return "switch"
        try:
            if picked == "download":
                _download(project, config)
            elif picked == "pdf":
                _for_chapters(project, "Make the PDF for", workflow.make_pdf, config)
            elif picked == "video":
                _for_chapters(project, "Make the video for", workflow.make_video, config)
            elif picked == "list":
                show_chapters(project)
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


def _download(project: str, config: RemangaConfig) -> None:
    listing = workflow.mangadex_chapters(project, config)
    if not listing:
        console.print("[yellow]MangaDex lists no chapters for this manga in the configured language.[/]")
        return
    available = [entry["chapter"] for entry in listing]
    have = sum(entry["status"] == "downloaded" for entry in listing)
    console.print(f"MangaDex has {len(available)} chapter(s): {available[0]} … {available[-1]} · "
                  f"{have} downloaded here")
    chapters = workflow.select_chapters(_ask_selection("Chapters to download"), available)
    if chapters:
        workflow.download(project, chapters, config)


def _for_chapters(project: str, label: str, step, config: RemangaConfig) -> None:
    available = show_chapters(project)
    if not available:
        return
    chapters = workflow.select_chapters(_ask_selection(f"{label} which chapters"), available)
    for chapter in chapters:
        console.print(f"\n[bold cyan]Chapter {chapter}[/]")
        step(project, chapter, config)
