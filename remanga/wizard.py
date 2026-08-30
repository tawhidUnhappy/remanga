"""The master interactive production wizard: project/chapter discovery followed by the
full download -> crop -> narrate -> synthesize -> mix -> render pipeline, in order -
or, in full-recap mode, compiling a whole project's chapters into one continuous video."""

from __future__ import annotations

from rich.prompt import Confirm, Prompt

from remanga import setup
from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, display_path, print_path, wrap_at_slashes
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.full_recap import FullRecapCompiler, chapter_sort_key, discover_chapters
from remanga.json_io import has_real_json_content
from remanga.paths import ensure_memory_file, get_chapter_dir, load_project_metadata
from remanga.status import get_chapter_status
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker
from remanga.wizard_prompts import select_chapter, select_or_create_project


def run_interactive_pipeline():
    """Master interactive production wizard with project discovery, resume guards, and setup option."""
    console.print("[bold]remanga[/] [dim]— interactive recap production[/]\n")

    config = RemangaConfig.load()

    # 1. Project Selection / Creation / Settings
    project = select_or_create_project(config)

    # 2. Single chapter, or the whole manga joined into one video?
    console.print(
        "\n[bold]1.[/] Process a chapter\n"
        "[bold]2.[/] Compile the whole project into one continuous video (full-recap)\n"
    )
    mode = Prompt.ask("[bold]Choose[/]", choices=["1", "2"], default="1")
    if mode == "2":
        _run_full_recap(project, config)
        return

    meta = load_project_metadata(project)
    saved_url = meta.get("manga_url", "")

    if saved_url:
        console.print(f"[dim]Saved MangaDex URL:[/] {wrap_at_slashes(saved_url)}")
        use_saved = Confirm.ask("Use saved MangaDex URL?", default=True)
        url = saved_url if use_saved else Prompt.ask("[bold]Enter MangaDex title URL/ID[/]").strip()
    else:
        url = Prompt.ask("[bold]Enter MangaDex title URL/ID[/]").strip()

    # 3. Chapter Selection
    chapter = select_chapter(project)
    chap_dir = get_chapter_dir(project, chapter)

    # 4. Reference Voice and BGM Validation
    setup.ensure_valid_voice_prompt(config, interactive=True)
    setup.ensure_valid_bgm(config, interactive=True)

    # 5. Status Overview
    status = get_chapter_status(project, chapter)
    package = config.cropper.package

    console.print()
    print_path(f"[bold]Workspace:[/] {display_path(chap_dir, wrap=False)}")
    console.print(f"[bold]Status:[/] {status['summary']}")
    console.print(f"[dim]Generate: panels (always) + sheets {'on' if package.sheets else 'off'}[/]")
    console.print(
        f"[dim]Package: "
        f"panels_zip {setup.bundle_state_str(package, package.panels_zip, package.panels_zip_splites)} | "
        f"pdf {'on' if package.pdf else 'off'} | pdf_splite {'on' if package.pdf_splite else 'off'} | "
        f"pdf_zip {'on' if package.pdf_zip else 'off'} | "
        f"pdf_zip_splite {'on' if package.pdf_zip_splite else 'off'} | "
        f"sheets_zip {'on' if package.sheets_zip else 'off'}[/]"
    )
    console.print(f"[dim]Render output: {config.video.width}x{config.video.height} ({config.video.background_style.title()} canvas)[/]\n")

    # What gets generated/zipped/PDF'd comes straight from config.json's
    # cropper.package settings (shown above) - it's a project-wide setting
    # like voice/BGM, not something to re-confirm every chapter. Run
    # `remanga setup-config` to change it.

    # =========================================================================
    # Step 1: Download Pages
    # =========================================================================
    console.print(f"[bold]Step 1 — Downloading Chapter {chapter}[/]")
    dl = MangaDexDownloader(config.downloader)
    dl.download_chapter(url, chapter, project)

    # =========================================================================
    # Step 2: Mark Panels (crops.json, via the Panel Marker web UI)
    # =========================================================================
    crops_path = chap_dir / "crops.json"
    if not has_real_json_content(crops_path):
        console.print(
            "\n[bold]Mark Panels[/]\n"
            "Opening the Panel Marker web UI. Mark each panel on every story page "
            f"(MAGI v3 pre-fills what it can find), then press "
            f"{'⌘S' if config.marker.auto_open_browser else 'Ctrl+S'} or click "
            "Save & Continue in the browser tab.\n"
        )
        launch_panel_marker(project, chapter, config.marker)
        console.print("[green]✓ Panels marked and crops.json saved.[/]")

    # =========================================================================
    # Step 3: Cropping Panels & Packaging Vision Uploads
    # =========================================================================
    console.print("\n[bold]Step 2 — Cropping Panels & Packaging Vision Uploads[/]")
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
            console.print(
                "\n[bold red]Nothing to upload:[/] no panels, sheets, or zip/PDF bundle exist for "
                "this chapter.\nRe-run the wizard and answer yes to \"Adjust what gets "
                "generated/zipped for this chapter?\", or run ./run.sh setup-config "
                "(step 2), and turn at least sheets on."
            )
            raise SystemExit(1)

        # Every actual path is printed via print_path, one per line, never
        # force-wrapped - a wrapped path breaks ctrl+click-to-open in an
        # editor's integrated terminal (VS Code, etc.).
        console.print(
            "\n[bold]Generate narration.json + memory.json[/]\n"
            f"1. Upload any one of the file(s) listed below to your LLM, along with prompts/narration.md"
            + (
                " and the current memory.json (required from chapter 2 onward, for story continuity)"
                if chapter_needs_memory else
                " and the current memory.json (for story continuity)" if memory_has_content else ""
            ) + ".\n"
            "[dim](each file already carries the project/manga/chapter identity itself - no need to type it in chat)[/]\n"
            "2. It replies with two JSON blocks - save each one into the matching path listed below.\n"
        )

        console.print("[bold]Chapter folder:[/]")
        print_path(f"  {display_path(chap_dir, wrap=False)}")

        console.print("\n[bold]Upload any one of:[/]")
        for kind, parts in upload_groups:
            note = (
                f"split into {len(parts)} parts, ≤{package.max_mb:g}MB each - upload all parts "
                f"together" if len(parts) > 1 else "one file"
            )
            console.print(f"  [dim]{kind}, {note}:[/]")
            for part in parts:
                print_path(f"    {display_path(part, wrap=False)}")

        console.print("\n[bold]Save its reply into:[/]")
        console.print("  narration.json")
        print_path(f"    {display_path(narration_path, wrap=False)}")
        console.print("  memory.json")
        print_path(f"    {display_path(memory_path, wrap=False)}")

        Prompt.ask("\n[bold]Press Enter once both files are saved and ready[/]")

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
                console.print(
                    f"\n[bold red]memory.json is still empty/missing.[/] From chapter 2 onward this "
                    f"is required, not optional - it's what carries story continuity (character "
                    f"names, prior events) forward from the last chapter. Save the LLM's memory.json "
                    f"reply to:\n{display_path(memory_path, wrap=False)}"
                )
                Prompt.ask("[bold]Press Enter once memory.json is saved[/]")

    # =========================================================================
    # Step 5: Synthesizing Vocal Audio via IndexTTS-2.5
    # =========================================================================
    console.print("\n[bold]Step 3 — Synthesizing Vocal Audio via IndexTTS-2.5[/]")
    tts = TTSEngine(config.tts, config.audio)
    tts.generate_narration_audio(project, chapter, interactive=True)

    # =========================================================================
    # Step 6: Mixing Master Audio Track & Loudnorm
    # =========================================================================
    console.print("\n[bold]Step 4 — Mixing Master Audio Track[/]")
    mixer = AudioProcessor(config.audio)
    mixer.mix_master_audio(project, chapter, interactive=True)

    # =========================================================================
    # Step 7: Render Final Video (1080p / 2K / 4K)
    # =========================================================================
    console.print(f"\n[bold]Step 5 — Rendering Final {config.video.height}p Recap Video[/]")
    renderer = VideoRenderer(config.system, config.video)
    final_video = renderer.render_video(project, chapter)

    console.print(f"\n[bold green]✓ Recap video complete[/] [dim]({config.video.width}x{config.video.height}, {config.video.background_style.title()} canvas)[/]")
    print_path(f"  {display_path(final_video, wrap=False)}")


def _run_full_recap(project: str, config: RemangaConfig) -> None:
    """Full-recap mode: no per-chapter download/mark/crop walkthrough - every
    chapter is expected to already have cropped panels and a narration.json
    (write those with the regular per-chapter flow first). This just picks
    which chapters to include, validates voice/BGM, and compiles."""
    chapters = discover_chapters(project)
    if not chapters:
        console.print(f"[bold red]No chapters found for '{project}'.[/]")
        return

    console.print(f"\n[dim]Chapters found: {', '.join(chapters)}[/]")
    choice = Prompt.ask(
        "[bold]Compile all of them, or a subset? (comma-separated chapter numbers, or Enter for all)[/]",
        default="",
    ).strip()
    selected = sorted({c.strip() for c in choice.split(",") if c.strip()}, key=chapter_sort_key) if choice else chapters

    setup.ensure_valid_voice_prompt(config, interactive=True)
    setup.ensure_valid_bgm(config, interactive=True)

    force = Confirm.ask("Force a full recompile even if already compiled?", default=False)

    console.print(f"\n[bold]Compiling {len(selected)} chapter(s) into one continuous video[/]")
    compiler = FullRecapCompiler(config)
    compiler.compile_full_manga(project, force=force, chapters=selected)
