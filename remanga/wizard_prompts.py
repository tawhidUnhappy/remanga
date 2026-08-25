"""Interactive project/chapter picker prompts used at the start of the production wizard,
including the resume-vs-restart offer for a chapter that already has generated progress."""

from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from remanga import reset
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.paths import list_projects
from remanga.setup_wizard import run_setup_wizard
from remanga.status import get_chapter_status


def select_or_create_project(config: RemangaConfig) -> str:
    """Interactively displays existing projects or configuration setup option."""
    existing_projects = list_projects()

    if existing_projects:
        table = Table(title="[bold cyan]📁 Existing Projects[/]", border_style="blue")
        table.add_column("#", style="bold yellow", width=4)
        table.add_column("Project Name", style="bold white")
        table.add_column("Chapters", style="green")
        table.add_column("Saved Manga Source", style="dim")

        for idx, p in enumerate(existing_projects, start=1):
            chaps_str = ", ".join(p["chapters"]) if p["chapters"] else "[dim]None[/]"
            src_str = p["manga_url"] or p["manga_id"] or "[dim]None[/]"
            table.add_row(str(idx), p["name"], chaps_str, src_str[:55] + ("..." if len(src_str) > 55 else ""))

        console.print(table)
        console.print("[dim]Select a project number, 'n' for new project, or 's' to configure settings (Voice/BGM/Resolution/Blur/Vision Format).[/]\n")

        choice = Prompt.ask("[bold cyan]Choose project number or enter new project name[/]", default="1").strip()
        if choice.lower() == "s":
            run_setup_wizard(config)
            return select_or_create_project(config)
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(existing_projects):
                return existing_projects[idx - 1]["name"]
        elif choice.lower() == "n":
            return Prompt.ask("[bold cyan]Enter new project name[/]").strip()
        elif choice:
            return choice

    return Prompt.ask("[bold cyan]Enter project name[/]", default="DefinitelyYandere").strip()


def offer_chapter_restart(project_name: str, chapter_num: str) -> None:
    """If the chosen chapter already has any generated progress beyond the downloaded pages
    (partially done or fully complete), asks whether to resume from where it left off or wipe
    it back to just the downloaded pages and restart from scratch. Restarting still requires a
    second, explicit confirmation before anything is actually deleted."""
    status = get_chapter_status(project_name, chapter_num)
    candidates = reset.restart_candidates(project_name, chapter_num)
    if not candidates:
        return  # nothing generated yet beyond the downloaded pages - nothing to choose between

    console.print(Panel(
        f"[bold yellow]Chapter {chapter_num} already has progress:[/] {status['summary']}\n"
        f"[dim]{len(candidates)} generated item(s) present (crops/panels/narration/audio/video).[/]",
        border_style="yellow"
    ))
    console.print(f"  [bold]1.[/] Resume Chapter {chapter_num} where it left off")
    console.print(f"  [bold]2.[/] Restart Chapter {chapter_num} from scratch")
    choice = Prompt.ask(
        "[bold cyan]Choose an option[/]",
        choices=["1", "2"],
        default="1",
    )
    if choice == "1":
        console.print(f"[dim]Resuming Chapter {chapter_num} from its current progress.[/]\n")
        return

    console.print("[bold red]The following will be permanently deleted:[/]")
    for c in candidates:
        console.print(f"  [dim]- {c}[/]")

    if Confirm.ask(
        f"[bold red]Confirm: permanently delete these {len(candidates)} item(s) for Chapter {chapter_num}? This cannot be undone.[/]",
        default=False,
    ):
        reset.restart_chapter(project_name, chapter_num)
        console.print(f"[bold green]✓ Chapter {chapter_num} reset. Downloaded pages kept — ready to reprocess.[/]\n")
    else:
        console.print(f"[dim]Restart cancelled. Resuming Chapter {chapter_num} from its current progress instead.[/]\n")


def select_chapter(project_name: str) -> str:
    """Interactively lists chapters with their production status for the chosen project."""
    existing_projects = {p["name"]: p for p in list_projects()}
    project_info = existing_projects.get(project_name)

    if project_info and project_info["chapters"]:
        table = Table(title=f"[bold cyan]📑 Chapters for '{project_name}'[/]", border_style="cyan")
        table.add_column("#", style="bold yellow", width=4)
        table.add_column("Chapter", style="bold white")
        table.add_column("Current Status", style="green")

        for idx, ch in enumerate(project_info["chapters"], start=1):
            status = get_chapter_status(project_name, ch)
            table.add_row(str(idx), f"Chapter {ch}", f"[{'green' if 'Ready' in status['summary'] else 'yellow'}]{status['summary']}[/]")

        console.print(table)
        console.print("[dim]Select a chapter number to resume, or type a new chapter number.[/]\n")

        default_ch = project_info["chapters"][-1]
        choice = Prompt.ask("[bold cyan]Enter chapter number to process[/]", default=str(default_ch)).strip()
        if choice.isdigit() and int(choice) <= len(project_info["chapters"]) and int(choice) >= 1:
            chapter = project_info["chapters"][int(choice) - 1]
        else:
            chapter = choice
    else:
        chapter = Prompt.ask("[bold cyan]Enter chapter number to process (e.g. 1 or 01)[/]", default="1").strip()

    offer_chapter_restart(project_name, chapter)
    return chapter
