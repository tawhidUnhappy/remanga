"""Interactive project/chapter picker prompts used at the start of the production wizard,
including the resume-vs-restart offer for a chapter that already has generated progress."""

from __future__ import annotations

from rich.prompt import Confirm, Prompt
from rich.table import Table

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import write_json
from remanga.paths import get_pipeline_path, list_projects, load_project_metadata, save_project_metadata
from remanga.setup_wizard import run_setup_wizard
from remanga.status import get_chapter_status


def _ensure_reading_direction(project_name: str) -> None:
    """Asks once per project (right-to-left for native Japanese manga,
    left-to-right for manhwa/manhua/webtoons and most Western comics) and
    persists it to project.json - the crop step raises a clear, actionable
    error if it's still missing by the time it needs it, so this is a
    convenience, not the only place it can be set. Native manga is the
    pipeline's overwhelming default, hence "right_to_left" pre-selected."""
    meta = load_project_metadata(project_name)
    if "reading_direction" in meta:
        return
    is_rtl = Confirm.ask(
        f"[bold]Is '{project_name}' read right-to-left[/] (Japanese manga convention - "
        "say no for manhwa/manhua/webtoons or Western comics)?",
        default=True,
    )
    save_project_metadata(project_name, {"reading_direction": "right_to_left" if is_rtl else "left_to_right"})


def select_or_create_project(config: RemangaConfig) -> str:
    """Interactively displays existing projects or configuration setup option,
    then ensures the chosen/new project has a reading_direction saved before
    handing its name back - one place this gets asked, regardless of which
    command the user goes on to run."""
    project_name = _pick_or_create_project(config)
    _ensure_reading_direction(project_name)
    return project_name


def _pick_or_create_project(config: RemangaConfig) -> str:
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
            return _pick_or_create_project(config)
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(existing_projects):
                return existing_projects[idx - 1]["name"]
        elif choice.lower() == "n":
            return Prompt.ask("[bold]Enter new project name[/]").strip()
        elif choice:
            return choice

    return Prompt.ask("[bold]Enter project name[/]", default="DefinitelyYandere").strip()


def edit_pipeline_steps(project_name: str, config: RemangaConfig) -> None:
    """Lets the user redefine this project's pipeline.json - which steps
    run, and in what order - as a comma-separated ordered list, checked
    against STEP_REGISTRY. If `crop` ends up in the chosen list, also offers
    the existing 'what to generate/zip' checklist (sheets/pdf/panels_zip/
    none of them) right here, so adjusting the pipeline and adjusting what
    the crop step actually produces are one stop instead of two (the same
    checklist remains reachable separately via `remanga setup-config`).
    Deferred import (remanga.pipeline pulls in the audio/video/webui/
    downloader/cropper modules - keeps that cost paid only when this path is
    actually taken)."""
    from remanga.pipeline import STEP_REGISTRY, load_pipeline

    console.print(f"\n[bold]Pipeline steps for '{project_name}'[/]\n[dim]Available steps, in their usual order:[/]")
    for step in STEP_REGISTRY:
        console.print(f"  [bold]{step.name}[/] [dim]— {step.description}[/]")

    current = load_pipeline(project_name)
    console.print(f"\n[dim]Current pipeline:[/] {', '.join(current)}")

    valid_names = {step.name for step in STEP_REGISTRY}
    while True:
        raw = Prompt.ask(
            "\n[bold]Enter the steps to run, comma-separated, in order[/]",
            default=", ".join(current),
        ).strip()
        chosen = [s.strip() for s in raw.split(",") if s.strip()]
        unknown = [s for s in chosen if s not in valid_names]
        if unknown:
            console.print(f"[bold red]Unknown step(s):[/] {', '.join(unknown)}. [dim]Valid: {', '.join(sorted(valid_names))}[/]")
            continue
        if not chosen:
            console.print("[bold red]At least one step is required.[/]")
            continue
        break

    write_json(get_pipeline_path(project_name), {"steps": chosen})
    console.print(f"[green]✓ Saved pipeline for '{project_name}':[/] {', '.join(chosen)}")

    if "crop" in chosen:
        package = config.cropper.package
        current_state = ", ".join(
            name for name in ("sheets", "sheets_zip", "sheets_folders", "pdf", "panels_zip")
            if getattr(package, name)
        ) or "nothing (panels/ only)"
        console.print(f"\n[dim]crop currently also generates:[/] {current_state}")
        if Confirm.ask(
            "[bold]Adjust what the crop step generates (sheets/zip/pdf/none)?[/]", default=False
        ):
            from remanga.setup import configure_vision_outputs

            configure_vision_outputs(config)


def select_chapter(project_name: str) -> str:
    """Interactively lists chapters with their production status for the chosen project and
    returns whichever one is picked. Purely a picker - doesn't offer to reset/restart anything;
    that's the standalone `restart` command's job (choose it from the main menu, with its own
    --mode choice, if that's what's actually wanted for a given chapter)."""
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

    return chapter
