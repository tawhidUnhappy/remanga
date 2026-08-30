"""Interactive project/chapter picker prompts used at the start of the production wizard,
including the resume-vs-restart offer for a chapter that already has generated progress."""

from __future__ import annotations

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
        table = Table(title="Existing Projects", show_edge=False)
        table.add_column("#", width=4)
        table.add_column("Project Name")
        table.add_column("Chapters")
        table.add_column("Saved Manga Source", style="dim")

        for idx, p in enumerate(existing_projects, start=1):
            chaps_str = ", ".join(p["chapters"]) if p["chapters"] else "[dim]none[/]"
            src_str = p["manga_url"] or p["manga_id"] or "[dim]none[/]"
            table.add_row(str(idx), p["name"], chaps_str, src_str[:55] + ("..." if len(src_str) > 55 else ""))

        console.print(table)
        console.print("[dim]Select a project number, 'n' for new project, or 's' for settings (voice/BGM/resolution/blur/vision format).[/]\n")

        choice = Prompt.ask("[bold]Choose project number or enter new project name[/]", default="1").strip()
        if choice.lower() == "s":
            run_setup_wizard(config)
            return select_or_create_project(config)
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(existing_projects):
                return existing_projects[idx - 1]["name"]
        elif choice.lower() == "n":
            return Prompt.ask("[bold]Enter new project name[/]").strip()
        elif choice:
            return choice

    return Prompt.ask("[bold]Enter project name[/]", default="DefinitelyYandere").strip()


# Restart menu choices below "1. Resume", in order from least to most destructive.
# mode: what this is called and how it's dispatched below. deletion_mode: the
# reset.py mode that actually determines what gets deleted - "remark" isn't a
# real reset.py mode, it deletes exactly like "marks_only" and then additionally
# reopens the Panel Marker (see the dispatch below). label: what the wizard
# prints for that menu line. kept: what survives, for the "Kept: ..."
# confirmation line once a mode is picked.
_RESTART_MENU = [
    ("soft", "soft", "Soft restart - keep crops.json, panels/, and narration.json; redo sheets/audio/video",
     "downloaded pages, crops.json, panels/, and narration.json"),
    ("remark", "marks_only", "Re-mark - keep crops.json; wipe everything else, then reopen the Panel Marker to adjust marks",
     "downloaded pages and crops.json (narration.json is emptied, not kept)"),
    ("marks_only", "marks_only", "Marks-only restart - keep crops.json; empty narration.json and redo everything after it",
     "downloaded pages and crops.json (narration.json is emptied, not kept)"),
    ("hard", "hard", "Hard restart - wipe everything, keep only the downloaded pages",
     "downloaded pages"),
]

_RESTART_KIND_LABELS = {
    "soft": "Soft restart",
    "remark": "Re-mark restart",
    "marks_only": "Marks-only restart",
    "hard": "Hard restart",
}


def offer_chapter_restart(project_name: str, chapter_num: str) -> None:
    """If the chosen chapter already has any generated progress beyond the downloaded pages
    (partially done or fully complete), asks whether to resume from where it left off or pick
    one of the restart levels in _RESTART_MENU. Any restart still requires a second, explicit
    confirmation before anything is actually deleted, and all of them re-verify the downloaded
    pages afterward (see reset.restart_chapter)."""
    status = get_chapter_status(project_name, chapter_num)
    hard_candidates = reset.restart_candidates(project_name, chapter_num, mode="hard")
    if not hard_candidates:
        return  # nothing generated yet beyond the downloaded pages - nothing to choose between

    console.print(
        f"\n[bold]Chapter {chapter_num} already has progress:[/] {status['summary']}\n"
        f"[dim]{len(hard_candidates)} generated item(s) present (crops/panels/narration/audio/video).[/]"
    )
    console.print(f"  1. Resume Chapter {chapter_num} where it left off")
    for i, (_, _, label, _) in enumerate(_RESTART_MENU, start=2):
        console.print(f"  {i}. {label}")
    choices = [str(i) for i in range(1, len(_RESTART_MENU) + 2)]
    choice = Prompt.ask("[bold]Choose an option[/]", choices=choices, default="1")
    if choice == "1":
        console.print(f"[dim]Resuming Chapter {chapter_num} from its current progress.[/]\n")
        return

    mode, deletion_mode, _, kept = _RESTART_MENU[int(choice) - 2]
    kind = _RESTART_KIND_LABELS[mode]
    candidates = reset.restart_candidates(project_name, chapter_num, mode=deletion_mode)
    if not candidates:
        console.print(f"[dim]Nothing to delete for a {kind.lower()} - everything it would keep is already all that's here.[/]\n")
        return

    console.print(f"[bold red]{kind}: the following will be permanently deleted:[/]")
    for c in candidates:
        console.print(f"  [dim]- {c}[/]")
    console.print(f"[dim]Kept: {kept}.[/]")

    if Confirm.ask(
        f"[bold red]Confirm: permanently delete these {len(candidates)} item(s) for Chapter {chapter_num}? This cannot be undone.[/]",
        default=False,
    ):
        reset.restart_chapter(project_name, chapter_num, mode=deletion_mode)
        console.print(f"[green]✓ Chapter {chapter_num} {kind.lower()} complete. Downloaded pages re-verified and kept — ready to reprocess.[/]\n")

        if mode == "remark":
            # Deferred imports: this module is loaded very early (project/
            # chapter selection), well before wizard.py normally needs
            # Flask/the marker's own deps - keep that cost paid only when
            # this path is actually taken.
            from remanga.config import RemangaConfig
            from remanga.webui import launch_and_wait as launch_panel_marker

            marker_config = RemangaConfig.load().marker
            console.print(
                f"\n[bold]Reopening the Panel Marker for Chapter {chapter_num}...[/]\n"
                f"Your existing marks are pre-loaded (MAGI won't touch them) - adjust anything, then "
                f"press {'⌘S' if marker_config.auto_open_browser else 'Ctrl+S'} or click "
                f"Save & Continue in the browser tab.\n"
            )
            launch_panel_marker(project_name, chapter_num, marker_config)
            console.print(f"[green]✓ Marks for Chapter {chapter_num} updated and saved.[/]\n")
    else:
        console.print(f"[dim]Restart cancelled. Resuming Chapter {chapter_num} from its current progress instead.[/]\n")


def select_chapter(project_name: str) -> str:
    """Interactively lists chapters with their production status for the chosen project."""
    existing_projects = {p["name"]: p for p in list_projects()}
    project_info = existing_projects.get(project_name)

    if project_info and project_info["chapters"]:
        table = Table(title=f"Chapters for '{project_name}'", show_edge=False)
        table.add_column("#", width=4)
        table.add_column("Chapter")
        table.add_column("Status")

        for idx, ch in enumerate(project_info["chapters"], start=1):
            status = get_chapter_status(project_name, ch)
            table.add_row(str(idx), f"Chapter {ch}", status["summary"])

        console.print(table)
        console.print("[dim]Select a chapter number to resume, or type a new chapter number.[/]\n")

        default_ch = project_info["chapters"][-1]
        choice = Prompt.ask("[bold]Enter chapter number to process[/]", default=str(default_ch)).strip()
        if choice.isdigit() and int(choice) <= len(project_info["chapters"]) and int(choice) >= 1:
            chapter = project_info["chapters"][int(choice) - 1]
        else:
            chapter = choice
    else:
        chapter = Prompt.ask("[bold]Enter chapter number to process (e.g. 1 or 01)[/]", default="1").strip()

    offer_chapter_restart(project_name, chapter)
    return chapter
