from __future__ import annotations

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from remanga import setup
from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.paths import get_chapter_dir, list_projects, load_project_metadata
from remanga.status import get_chapter_status
from remanga.video import VideoRenderer

console = Console()


def _select_or_create_project(config: RemangaConfig) -> str:
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
            setup.run_setup_wizard(config)
            return _select_or_create_project(config)
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(existing_projects):
                return existing_projects[idx - 1]["name"]
        elif choice.lower() == "n":
            return Prompt.ask("[bold cyan]Enter new project name[/]").strip()
        elif choice:
            return choice

    return Prompt.ask("[bold cyan]Enter project name[/]", default="DefinitelyYandere").strip()


def _select_chapter(project_name: str) -> str:
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
            return project_info["chapters"][int(choice) - 1]
        return choice

    return Prompt.ask("[bold cyan]Enter chapter number to process (e.g. 1 or 01)[/]", default="1").strip()


def run_interactive_pipeline():
    """Master interactive production wizard with project discovery, resume guards, and setup option."""
    console.print(Panel("[bold magenta]✨ remanga: Interactive Recap Production Engine (IndexTTS-2.5)[/]", border_style="magenta"))

    config = RemangaConfig.load()

    # 1. Project Selection / Creation / Settings
    project = _select_or_create_project(config)
    meta = load_project_metadata(project)
    saved_url = meta.get("manga_url", "")

    if saved_url:
        console.print(f"[green]Found saved MangaDex URL:[/] {saved_url}")
        use_saved = Confirm.ask("Use saved MangaDex URL?", default=True)
        url = saved_url if use_saved else Prompt.ask("[bold cyan]Enter MangaDex title URL/ID[/]").strip()
    else:
        url = Prompt.ask("[bold cyan]Enter MangaDex title URL/ID[/]").strip()

    # 2. Chapter Selection
    chapter = _select_chapter(project)
    chap_dir = get_chapter_dir(project, chapter)

    # 3. Reference Voice, BGM, and Vision Packaging Preference Validation
    setup.ensure_valid_vision_asset_preference(config, interactive=True)
    setup.ensure_valid_voice_prompt(config, interactive=True)
    setup.ensure_valid_bgm(config, interactive=True)

    # 4. Status Overview
    status = get_chapter_status(project, chapter)
    asset_mode = config.cropper.vision_asset_type
    archive_name = "panels.zip" if asset_mode == "panels" else "sheets.zip"

    console.print(f"\n[bold]Current Chapter Workspace:[/] {chap_dir.resolve()}")
    console.print(f"[bold]Current Chapter Status:[/] [{'green' if 'Ready' in status['summary'] else 'yellow'}]{status['summary']}[/]")
    console.print(f"[bold]Vision Packaging Format:[/] {asset_mode.title()} ({archive_name})")
    console.print(f"[bold]Render Output:[/] {config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)\n")

    # =========================================================================
    # Step 1: Download Pages
    # =========================================================================
    console.print(f"\n[bold blue]=== Step 1: Downloading Chapter {chapter} ===[/]")
    dl = MangaDexDownloader(config.downloader)
    dl.download_chapter(url, chapter, project)

    # =========================================================================
    # Step 2: Crop Instructions (crops.json)
    # =========================================================================
    crops_path = chap_dir / "crops.json"
    if not crops_path.exists() or crops_path.stat().st_size <= 10:
        crops_path.parent.mkdir(parents=True, exist_ok=True)
        crops_path.write_text("{}", encoding="utf-8")
        console.print(Panel(
            f"[bold yellow]Action Required:[/]\n"
            f"1. Upload [bold]{chap_dir}/pages.zip[/] along with [bold]prompts/crop_generation_prompt.md[/] to your LLM.\n"
            f"2. Save the resulting JSON directly into:\n   [bold green]{crops_path.resolve()}[/]",
            title="[bold white]Generate crops.json[/]",
            border_style="yellow"
        ))
        Prompt.ask("[bold cyan]Press Enter once crops.json is saved and ready[/]")

    # =========================================================================
    # Step 3: Cropping Panels & Building Vision Archive (sheets.zip or panels.zip)
    # =========================================================================
    console.print(f"\n[bold blue]=== Step 2: Cropping Panels & Compiling {archive_name} ===[/]")
    cropper = CoordinateCropper(config.cropper)
    cropper.crop_chapter_from_json(project, chapter)

    # =========================================================================
    # Step 4: Narration Script (narration.json)
    # =========================================================================
    narration_path = chap_dir / "narration.json"
    target_vision_archive = chap_dir / archive_name

    if not narration_path.exists() or narration_path.stat().st_size <= 10:
        narration_path.parent.mkdir(parents=True, exist_ok=True)
        narration_path.write_text("{}", encoding="utf-8")
        console.print(Panel(
            f"[bold yellow]Action Required:[/]\n"
            f"1. Upload [bold]{target_vision_archive.resolve()}[/] along with [bold]prompts/narration_generation_prompt.md[/] to your LLM.\n"
            f"2. Save the resulting narration JSON directly into:\n   [bold green]{narration_path.resolve()}[/]",
            title="[bold white]Generate narration.json[/]",
            border_style="yellow"
        ))
        Prompt.ask("[bold cyan]Press Enter once narration.json is saved and ready[/]")

    # =========================================================================
    # Step 5: Synthesizing Vocal Audio via IndexTTS-2.5
    # =========================================================================
    console.print(f"\n[bold blue]=== Step 3: Synthesizing Vocal Audio via IndexTTS-2.5 (Monotone / Zero-Emotion) ===[/]")
    tts = TTSEngine(config.tts, config.audio)
    tts.generate_narration_audio(project, chapter, interactive=True)

    # =========================================================================
    # Step 6: Mixing Master Audio Track & Loudnorm
    # =========================================================================
    console.print(f"\n[bold blue]=== Step 4: Mixing Master Audio Track ===[/]")
    mixer = AudioProcessor(config.audio)
    mixer.mix_master_audio(project, chapter, interactive=True)

    # =========================================================================
    # Step 7: Render Final Video (1080p / 2K / 4K)
    # =========================================================================
    console.print(f"\n[bold blue]=== Step 5: Rendering Final {config.video.height}p Recap Video ===[/]")
    renderer = VideoRenderer(config.system, config.video)
    final_video = renderer.render_video(project, chapter)

    console.print(Panel(
        f"[bold green]🎉 Recap Video Production Complete![/]\n\n"
        f"[bold white]Output File:[/] {final_video.resolve()}\n"
        f"[bold white]Resolution:[/] {config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)\n"
        f"[bold white]Vision Format:[/] {asset_mode.title()} ({archive_name})",
        title="[bold green]Success[/]",
        border_style="green"
    ))