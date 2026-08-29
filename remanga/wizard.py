"""The master interactive production wizard: project/chapter discovery followed by the
full download -> crop -> narrate -> synthesize -> mix -> render pipeline, in order."""

from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from remanga import setup
from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.json_io import has_real_json_content
from remanga.paths import ensure_memory_file, get_chapter_dir, load_project_metadata
from remanga.status import get_chapter_status
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker
from remanga.wizard_prompts import select_chapter, select_or_create_project


def run_interactive_pipeline():
    """Master interactive production wizard with project discovery, resume guards, and setup option."""
    console.print(Panel("[bold magenta]✨ remanga: Interactive Recap Production Engine (IndexTTS-2.5)[/]", border_style="magenta"))

    config = RemangaConfig.load()

    # 1. Project Selection / Creation / Settings
    project = select_or_create_project(config)
    meta = load_project_metadata(project)
    saved_url = meta.get("manga_url", "")

    if saved_url:
        console.print(f"[green]Found saved MangaDex URL:[/] {saved_url}")
        use_saved = Confirm.ask("Use saved MangaDex URL?", default=True)
        url = saved_url if use_saved else Prompt.ask("[bold cyan]Enter MangaDex title URL/ID[/]").strip()
    else:
        url = Prompt.ask("[bold cyan]Enter MangaDex title URL/ID[/]").strip()

    # 2. Chapter Selection
    chapter = select_chapter(project)
    chap_dir = get_chapter_dir(project, chapter)

    # 3. Reference Voice, BGM, and Vision Packaging Preference Validation
    setup.ensure_valid_vision_asset_preference(config, interactive=True)
    setup.ensure_valid_voice_prompt(config, interactive=True)
    setup.ensure_valid_bgm(config, interactive=True)

    # 4. Status Overview
    status = get_chapter_status(project, chapter)
    asset_mode = config.cropper.vision_asset_type
    archive_name = config.cropper.expected_zip_name

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
    # Step 2: Mark Panels (crops.json, via the Panel Marker web UI)
    # =========================================================================
    crops_path = chap_dir / "crops.json"
    if not has_real_json_content(crops_path):
        console.print(Panel(
            f"[bold yellow]Opening the Panel Marker web UI...[/]\n"
            f"Mark each panel on every story page (MAGI v3 pre-fills what it can find), "
            f"then press [bold]{'⌘S' if config.marker.auto_open_browser else 'Ctrl+S'}[/] or click "
            f"[bold]Save & Continue[/] in the browser tab.",
            title="[bold white]Mark Panels[/]",
            border_style="yellow"
        ))
        launch_panel_marker(project, chapter, config.marker)
        console.print("[bold green]✓ Panels marked and crops.json saved.[/]")

    # =========================================================================
    # Step 3: Cropping Panels & Building Vision Archive (sheets.zip or panels.zip)
    # =========================================================================
    console.print(f"\n[bold blue]=== Step 2: Cropping Panels & Compiling {archive_name} ===[/]")
    cropper = CoordinateCropper(config.cropper)
    cropper.crop_chapter_from_json(project, chapter)

    # =========================================================================
    # Step 4: Narration Script + Continuity Memory (narration.json + memory.json)
    # =========================================================================
    narration_path = chap_dir / "narration.json"
    target_vision_archive = chap_dir / archive_name
    llm_pdf_parts = sorted((chap_dir / "panels_pdf").glob("panels_*.pdf")) if config.cropper.llm_bundle.pdf_enabled else []
    llm_zip_parts = sorted((chap_dir / "panels_zip").glob("panels_*.zip")) if config.cropper.llm_bundle.zip_enabled else []
    memory_path = ensure_memory_file(project)
    memory_has_content = has_real_json_content(memory_path)

    if not has_real_json_content(narration_path):
        narration_path.parent.mkdir(parents=True, exist_ok=True)
        narration_path.write_text("", encoding="utf-8")
        # Prefer the PDF bundle when both are enabled - a single PDF is the
        # most universally-accepted upload shape across LLM chat interfaces,
        # more so than a zip of individual images. Either is a same-quality,
        # smaller-or-equal-sized alternative to the primary archive; upload
        # only one, never a mix (see prompts/narration.md's Chapter Identity).
        bundle_parts, bundle_kind = (llm_pdf_parts, "PDF") if llm_pdf_parts else (llm_zip_parts, "zip")
        if bundle_parts:
            size_note = (
                f"split into {len(bundle_parts)} parts, each ≤{config.cropper.llm_bundle.max_mb:g}MB - upload every "
                f"part together" if len(bundle_parts) > 1 else "one file"
            )
            upload_line = (
                f"1. Upload [bold]{', '.join(p.name for p in bundle_parts)}[/] "
                f"(in {bundle_parts[0].parent.resolve()}) along with [bold]prompts/narration.md[/] to your LLM "
                f"[dim](a {bundle_kind} bundle, same panels losslessly re-encoded smaller, {size_note}; "
                f"{target_vision_archive.resolve()} is the same panels as one full-quality archive if you'd "
                f"rather use that instead)[/]"
            )
        else:
            upload_line = f"1. Upload [bold]{target_vision_archive.resolve()}[/] along with [bold]prompts/narration.md[/] to your LLM"
        console.print(Panel(
            f"[bold yellow]Action Required:[/]\n"
            f"{upload_line}"
            + (f", plus the current [bold]{memory_path.resolve()}[/] for story continuity" if memory_has_content else "")
            + f" [dim](each carries the project name, manga name/URL, and chapter number itself - as a "
            f"chapter_info.json in a zip, or as page 1 in a PDF - so the LLM reads those itself, no need to "
            f"state them in chat)[/].\n"
            f"2. It replies with two JSON blocks - save each one into its own file:\n"
            f"   [bold green]{narration_path.resolve()}[/]  (narration.json)\n"
            f"   [bold green]{memory_path.resolve()}[/]  (memory.json)",
            title="[bold white]Generate narration.json + memory.json[/]",
            border_style="yellow"
        ))
        Prompt.ask("[bold cyan]Press Enter once both files are saved and ready[/]")

    # =========================================================================
    # Step 5: Synthesizing Vocal Audio via IndexTTS-2.5
    # =========================================================================
    console.print(f"\n[bold blue]=== Step 3: Synthesizing Vocal Audio via IndexTTS-2.5 ===[/]")
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
