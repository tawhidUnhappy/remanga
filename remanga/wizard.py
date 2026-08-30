"""The master interactive production wizard: project/chapter discovery followed by the
full download -> crop -> narrate -> synthesize -> mix -> render pipeline, in order."""

from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from remanga import setup
from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, display_path, wrap_at_slashes
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
        console.print(f"[green]Found saved MangaDex URL:[/] {wrap_at_slashes(saved_url)}")
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

    archive_status = archive_name if config.cropper.create_zip else "not built - create_zip is off"
    console.print(f"\n[bold]Current Chapter Workspace:[/] {display_path(chap_dir)}")
    console.print(f"[bold]Current Chapter Status:[/] [{'green' if 'Ready' in status['summary'] else 'yellow'}]{status['summary']}[/]")
    console.print(f"[bold]Vision Packaging Format:[/] {asset_mode.title()} ({archive_status})")
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
    crop_step_title = f"Cropping Panels & Compiling {archive_name}" if config.cropper.create_zip else "Cropping Panels"
    console.print(f"\n[bold blue]=== Step 2: {crop_step_title} ===[/]")
    cropper = CoordinateCropper(config.cropper)
    cropper.crop_chapter_from_json(project, chapter)

    # =========================================================================
    # Step 4: Narration Script + Continuity Memory (narration.json + memory.json)
    # =========================================================================
    narration_path = chap_dir / "narration.json"
    target_vision_archive = chap_dir / archive_name
    llm_pdf_parts = sorted((chap_dir / "panels_pdf").glob("panels_*.pdf")) if config.cropper.llm_bundle.pdf_active else []
    llm_zip_parts = sorted((chap_dir / "panels_zip").glob("panels_*.zip")) if config.cropper.llm_bundle.zip_active else []
    llm_sheets_parts = sorted((chap_dir / "sheets_zip").glob("sheets_*.zip")) if config.cropper.llm_bundle.sheets_active else []
    memory_path = ensure_memory_file(project)
    memory_has_content = has_real_json_content(memory_path)

    if not has_real_json_content(narration_path):
        narration_path.parent.mkdir(parents=True, exist_ok=True)
        narration_path.write_text("", encoding="utf-8")

        def _bundle_line(parts, kind: str) -> str:
            names = ", ".join(p.name for p in parts)
            location = f"{parts[0].parent.name}/"
            size_note = (
                f"split into {len(parts)} parts, ≤{config.cropper.llm_bundle.max_mb:g}MB each" if len(parts) > 1
                else "one file"
            )
            return f"  • [bold]{location}{{{names}}}[/]  —  {kind}, {size_note}" if len(parts) > 1 \
                else f"  • [bold]{location}{names}[/]  —  {kind}, {size_note}"

        # Just a plain list of everything actually available this run - no
        # priority pick, no "or use X instead" hedging. Upload any ONE of
        # these, never a mix (see prompts/narration.md's Chapter Identity).
        # Paths are shown relative to the chapter folder printed once above
        # the list, instead of repeating the full absolute path per line.
        upload_options = []
        if llm_pdf_parts:
            upload_options.append(_bundle_line(llm_pdf_parts, "PDF bundle"))
        if llm_zip_parts:
            upload_options.append(_bundle_line(llm_zip_parts, "zip bundle"))
        if llm_sheets_parts:
            upload_options.append(_bundle_line(llm_sheets_parts, "sheets zip bundle"))
        if config.cropper.create_zip:
            upload_options.append(f"  • [bold]{target_vision_archive.name}[/]  —  full-quality primary archive")
        if not upload_options:
            upload_options.append(f"  • [bold]{target_vision_archive.name}[/]")

        console.print(Panel(
            f"[bold]Chapter folder:[/] {display_path(chap_dir)}\n\n"
            f"[bold yellow]Action Required:[/]\n"
            f"1. Upload [bold]any one[/] of these to your LLM, along with [bold]prompts/narration.md[/]"
            + (" and the current memory.json below (story continuity)" if memory_has_content else "") + ":\n"
            + "\n".join(upload_options) + "\n"
            f"[dim](each file already carries the project/manga/chapter identity itself - no need to type it in "
            f"chat)[/]\n\n"
            f"2. Save its reply into:\n"
            f"  • [bold green]narration.json[/]  (in the chapter folder above)\n"
            f"  • [bold green]memory.json[/]  ({display_path(memory_path)})",
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
        f"[bold white]Output File:[/] {display_path(final_video)}\n"
        f"[bold white]Resolution:[/] {config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)\n"
        f"[bold white]Vision Format:[/] {asset_mode.title()} ({archive_name})",
        title="[bold green]Success[/]",
        border_style="green"
    ))
