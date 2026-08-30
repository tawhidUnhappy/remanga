"""The master interactive production wizard: project/chapter discovery followed by the
full download -> crop -> narrate -> synthesize -> mix -> render pipeline, in order."""

from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from remanga import setup
from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, display_path, print_path, wrap_at_slashes
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

    # 3. Reference Voice and BGM Validation
    setup.ensure_valid_voice_prompt(config, interactive=True)
    setup.ensure_valid_bgm(config, interactive=True)

    # 4. Status Overview
    status = get_chapter_status(project, chapter)
    package = config.cropper.package

    console.print()
    print_path(f"[bold]Current Chapter Workspace:[/] {display_path(chap_dir, wrap=False)}")
    console.print(f"[bold]Current Chapter Status:[/] [{'green' if 'Ready' in status['summary'] else 'yellow'}]{status['summary']}[/]")
    console.print(f"[bold]Generate:[/] panels (always) + sheets {'on' if package.sheets else 'off'}")
    console.print(
        f"[bold]Package (zip/PDF for upload):[/] "
        f"panels_zip {setup.bundle_state_str(package, package.panels_zip, package.panels_zip_splites)} | "
        f"pdf {'on' if package.pdf else 'off'} | pdf_splite {'on' if package.pdf_splite else 'off'} | "
        f"pdf_zip {'on' if package.pdf_zip else 'off'} | "
        f"pdf_zip_splite {'on' if package.pdf_zip_splite else 'off'} | "
        f"sheets_zip {'on' if package.sheets_zip else 'off'}"
    )
    console.print(f"[bold]Render Output:[/] {config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)\n")

    # What gets generated/zipped/PDF'd comes straight from config.json's
    # cropper.package settings (shown above) - it's a project-wide setting
    # like voice/BGM, not something to re-confirm every chapter. Run
    # `remanga setup-config` to change it.

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
    # Step 3: Cropping Panels & Packaging Vision Uploads
    # =========================================================================
    console.print("\n[bold blue]=== Step 2: Cropping Panels & Packaging Vision Uploads ===[/]")
    cropper = CoordinateCropper(config.cropper)
    cropper.crop_chapter_from_json(project, chapter)

    # =========================================================================
    # Step 4: Narration Script + Continuity Memory (narration.json + memory.json)
    # =========================================================================
    narration_path = chap_dir / "narration.json"
    llm_pdf_parts = sorted((chap_dir / "panels_pdf").glob("panels_*.pdf")) + sorted((chap_dir / "panels_pdf").glob("panels_*.zip")) if package.pdf_active else []
    llm_zip_parts = sorted((chap_dir / "panels_zip").glob("panels_*.zip")) if package.panels_zip_active else []
    llm_sheets_parts = sorted((chap_dir / "sheets_zip").glob("sheets_*.zip")) if package.sheets_zip_active else []
    memory_path = ensure_memory_file(project)
    memory_has_content = has_real_json_content(memory_path)
    chapter_needs_memory = False
    try:
        chapter_needs_memory = float(chapter) >= 2
    except ValueError:
        pass

    if not has_real_json_content(narration_path):
        narration_path.parent.mkdir(parents=True, exist_ok=True)
        narration_path.write_text("", encoding="utf-8")

        # Just a plain list of everything actually available this run - no
        # priority pick, no "or use X instead" hedging. Upload any ONE of
        # these, never a mix (see prompts/narration.md's Chapter Identity).
        upload_groups = []
        if llm_pdf_parts:
            upload_groups.append(("PDF bundle", llm_pdf_parts))
        if llm_zip_parts:
            upload_groups.append(("zip bundle", llm_zip_parts))
        if llm_sheets_parts:
            upload_groups.append(("sheets zip bundle", llm_sheets_parts))

        # No zip/PDF format is active - that's a deliberate, valid config
        # for LLMs whose upload interface won't accept a zip or PDF
        # attachment at all, not an error. Fall back to whatever raw,
        # unpackaged images are already sitting on disk: the unzipped
        # sheets/ directory first (denser, fewer files, cheaper on vision
        # tokens), then the always-generated panels/ directory as a last
        # resort.
        if not upload_groups:
            raw_sheets_parts = sorted(
                p for p in (chap_dir / "sheets").glob("*") if p.is_file()
            ) if package.sheets else []
            if raw_sheets_parts:
                upload_groups.append(("sheets (unzipped)", raw_sheets_parts))

        if not upload_groups:
            raw_panels_parts = sorted(
                p for p in (chap_dir / "panels").glob("*") if p.is_file()
            )
            if raw_panels_parts:
                upload_groups.append(("panels (unzipped)", raw_panels_parts))

        # Truly nothing was built for this chapter at all (crop step must
        # have failed or produced no output) - tell the user exactly how to
        # fix it instead of silently printing an empty upload list.
        if not upload_groups:
            console.print(Panel(
                "[bold red]Nothing to upload:[/] no panels, sheets, or zip/PDF bundle exist for "
                "this chapter.\nRe-run the wizard and answer [bold]yes[/] to \"Adjust what gets "
                "generated/zipped for this chapter?\", or run [bold]./run.sh setup-config[/] "
                "(step 2), and turn at least [bold]sheets[/] on.",
                title="[bold white]No Vision Archive Available[/]",
                border_style="red"
            ))
            raise SystemExit(1)

        # Instructions live in the Panel; every actual path is printed after
        # it via print_path, one per line, never inside the Panel's border.
        # A Panel has to fit its content inside a fixed-width box, so it
        # force-wraps anything too long to fit - which is exactly what
        # breaks ctrl+click-to-open on a path in an editor's integrated
        # terminal (VS Code, etc.): the terminal can only turn one
        # continuous line into a link, not one Rich has hard-wrapped in two.
        console.print(Panel(
            f"[bold yellow]Action Required:[/]\n"
            f"1. Upload [bold]any one[/] of the file(s) listed below to your LLM, along with "
            f"[bold]prompts/narration.md[/]"
            + (
                " and the current memory.json ([bold]required[/] from chapter 2 onward, for story continuity)"
                if chapter_needs_memory else
                " and the current memory.json (for story continuity)" if memory_has_content else ""
            ) + ".\n"
            f"[dim](each file already carries the project/manga/chapter identity itself - no need to type it in "
            f"chat)[/]\n\n"
            f"2. It replies with two JSON blocks - save each one into the matching path listed below.",
            title="[bold white]Generate narration.json + memory.json[/]",
            border_style="yellow"
        ))

        console.print("\n[bold]Chapter folder:[/]")
        print_path(f"  {display_path(chap_dir, wrap=False)}")

        console.print("\n[bold]Upload any [underline]one[/] of:[/]")
        for kind, parts in upload_groups:
            note = (
                f"split into {len(parts)} parts, ≤{package.max_mb:g}MB each - upload all parts "
                f"together" if len(parts) > 1 else "one file"
            )
            console.print(f"  [dim]{kind}, {note}:[/]")
            for part in parts:
                print_path(f"    {display_path(part, wrap=False)}")

        console.print("\n[bold]Save its reply into:[/]")
        console.print("  [bold green]narration.json[/]")
        print_path(f"    {display_path(narration_path, wrap=False)}")
        console.print("  [bold green]memory.json[/]")
        print_path(f"    {display_path(memory_path, wrap=False)}")

        Prompt.ask("\n[bold cyan]Press Enter once both files are saved and ready[/]")

        # Starting chapter 2, memory.json isn't optional anymore - it's the
        # only thing carrying story continuity from the previous chapter
        # forward, so a chapter 2+ run with no real memory.json content is
        # almost certainly a forgotten upload/save step, not a deliberate
        # choice. Chapter 1 is exempt (nothing to carry continuity from
        # yet). Chapter numbers that don't parse as plain numbers (a
        # special/bonus chapter label) skip this check entirely rather than
        # guessing.
        if chapter_needs_memory:
            while not has_real_json_content(memory_path):
                console.print(Panel(
                    f"[bold red]memory.json is still empty/missing.[/] From chapter 2 onward this "
                    f"is required, not optional - it's what carries story continuity (character "
                    f"names, prior events) forward from the last chapter. Save the LLM's memory.json "
                    f"reply to:\n{display_path(memory_path, wrap=False)}",
                    title="[bold white]Continuity Memory Required[/]",
                    border_style="red"
                ))
                Prompt.ask("[bold cyan]Press Enter once memory.json is saved[/]")

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
        f"[bold white]Resolution:[/] {config.video.width}x{config.video.height} ({config.video.background_style.title()} Canvas)",
        title="[bold green]Success[/]",
        border_style="green"
    ))
    console.print("[bold white]Output File:[/]")
    print_path(f"  {display_path(final_video, wrap=False)}")
