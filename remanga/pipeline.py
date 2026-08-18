from __future__ import annotations

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig, get_chapter_dir, load_project_metadata
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.video import VideoRenderer

console = Console()


def run_interactive_pipeline():
    """Master interactive production wizard without duplicating CLI logic."""
    console.print(Panel("[bold magenta]✨ remanga: Interactive Recap Production Engine (IndexTTS-2.5)[/]", border_style="magenta"))

    config = RemangaConfig.load()

    # 1. Project & Chapter Selection
    project = Prompt.ask("[bold cyan]Enter project name[/]", default="DefinitelyYandere").strip()
    meta = load_project_metadata(project)
    saved_url = meta.get("manga_url", "")

    if saved_url:
        console.print(f"[green]Found saved MangaDex URL:[/] {saved_url}")
        use_saved = Confirm.ask("Use saved MangaDex URL?", default=True)
        url = saved_url if use_saved else Prompt.ask("[bold cyan]Enter MangaDex title URL/ID[/]").strip()
    else:
        url = Prompt.ask("[bold cyan]Enter MangaDex title URL/ID[/]").strip()

    chapter = Prompt.ask("[bold cyan]Enter chapter number to process (e.g. 1 or 01)[/]", default="1").strip()
    chap_dir = get_chapter_dir(project, chapter)

    # 2. Reference Voice & BGM Path Validation
    config.ensure_valid_voice_prompt(interactive=True)
    config.ensure_valid_bgm(interactive=True)

    # 3. Download Pages
    console.print(f"\n[bold blue]=== Step 1: Downloading Chapter {chapter} ===[/]")
    dl = MangaDexDownloader(config.downloader)
    dl.download_chapter(url, chapter, project)

    # 4. Check crops.json
    crops_path = chap_dir / "crops.json"
    if not crops_path.exists() or crops_path.stat().st_size == 0:
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

    # 5. Crop Panels & Build sheets.zip
    console.print(f"\n[bold blue]=== Step 2: Cropping Panels & Compiling sheets.zip ===[/]")
    cropper = CoordinateCropper(config.cropper)
    cropper.crop_chapter_from_json(project, chapter)

    # 6. Check narration.json
    narration_path = chap_dir / "narration.json"
    if not narration_path.exists() or narration_path.stat().st_size == 0:
        narration_path.parent.mkdir(parents=True, exist_ok=True)
        narration_path.write_text("{}", encoding="utf-8")
        console.print(Panel(
            f"[bold yellow]Action Required:[/]\n"
            f"1. Upload [bold]{chap_dir}/sheets.zip[/] along with [bold]prompts/narration_generation_prompt.md[/] to your LLM.\n"
            f"2. Save the resulting narration JSON directly into:\n   [bold green]{narration_path.resolve()}[/]",
            title="[bold white]Generate narration.json[/]",
            border_style="yellow"
        ))
        Prompt.ask("[bold cyan]Press Enter once narration.json is saved and ready[/]")

    # 7. Synthesize Speech via IndexTTS-2.5
    console.print(f"\n[bold blue]=== Step 3: Synthesizing Vocal Audio via IndexTTS-2.5 ===[/]")
    tts = TTSEngine(config.tts, config.audio)
    tts.generate_narration_audio(project, chapter, interactive=True)

    # 8. Mix Master Audio & Loudnorm
    console.print(f"\n[bold blue]=== Step 4: Mixing Master Audio Track ===[/]")
    mixer = AudioProcessor(config.audio)
    mixer.mix_master_audio(project, chapter, interactive=True)

    # 9. Render Final MP4
    console.print(f"\n[bold blue]=== Step 5: Rendering Final 1080p Recap Video ===[/]")
    renderer = VideoRenderer(config.system, config.video)
    final_video = renderer.render_video(project, chapter)

    console.print(Panel(
        f"[bold green]🎉 Recap Video Production Complete![/]\n\n"
        f"[bold white]Output File:[/] {final_video.resolve()}",
        title="[bold green]Success[/]",
        border_style="green"
    ))