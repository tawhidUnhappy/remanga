"""The master interactive production wizard: project/chapter discovery followed by the
full download -> crop -> narrate -> synthesize -> mix -> render pipeline, in order -
or, in full-recap mode, compiling a whole project's chapters into one continuous video."""

from __future__ import annotations

from typing import Any, Callable, Dict

from rich.prompt import Confirm, Prompt
from rich.table import Table

from remanga import setup
from remanga.commands import COMMAND_REGISTRY, Param
from remanga.config import RemangaConfig
from remanga.console import console, display_path, print_path, wrap_at_slashes
from remanga.cropper import CoordinateCropper
from remanga.full_recap import discover_chapters
from remanga.pipeline import load_pipeline, run_pipeline
from remanga.verify import verify_project
from remanga.json_io import has_real_json_content, read_json_or
from remanga.paths import (
    ensure_global_lessons_file, ensure_memory_file, get_chapter_dir, get_global_lessons_path,
    get_narration_review_path, get_panels_pdf_dir, get_panels_zip_dir, get_sheets_dir,
    get_sheets_zip_dir, list_projects, load_project_metadata, save_project_metadata,
)
from remanga.status import get_chapter_status
from remanga.webui import launch_and_wait as launch_panel_marker
from remanga.webui import launch_and_wait_reviewer, launch_and_wait_writer
from remanga.wizard_prompts import edit_pipeline_steps, select_chapter, select_or_create_project


def run_narration_review_loop(project: str, chapter: str, config: RemangaConfig) -> None:
    """Opens the Narration Reviewer web UI on the chapter's current
    narration.json, then - if the user flagged anything - walks them through
    handing narration_review.json (plus memory.json and the global lessons
    file) to the LLM for a fix pass, pasting the corrected narration.json (+
    updated memory.json / narration_lessons.json) back, and reopening the
    reviewer for another round. Repeats for as many rounds as the user wants;
    returns as soon as a round comes back with nothing flagged (or the user
    explicitly approves with zero flags). A no-op if narration.json isn't
    written yet - nothing to review."""
    chap_dir = get_chapter_dir(project, chapter)
    narration_path = chap_dir / "narration.json"
    if not has_real_json_content(narration_path):
        return

    memory_path = ensure_memory_file(project)
    lessons_path = ensure_global_lessons_file()
    review_path = get_narration_review_path(project, chapter)

    while True:
        console.print(
            "\n[bold]Review Narration[/]\n"
            "Opening the Narration Reviewer web UI. Flag any panel whose narration is wrong "
            "and note what's wrong with it, then click Approve (nothing flagged) or Submit."
        )
        launch_and_wait_reviewer(project, chapter, config.reviewer)

        if not has_real_json_content(review_path):
            console.print("[green]✓ Narration approved - no issues flagged.[/]")
            return

        review = read_json_or(review_path, {})
        if review.get("flagged_count", 0) == 0:
            console.print("[green]✓ Narration approved - no issues flagged.[/]")
            return

        console.print(
            f"\n[bold]{review['flagged_count']} panel(s) flagged.[/] Send these files to your LLM for a fix pass:\n"
            "[dim](each already carries the project/manga/chapter identity - no need to type it in chat)[/]\n"
        )
        console.print("[bold]Upload:[/]")
        console.print("  prompts/narration_review.md  [dim](the fix-pass prompt)[/]")
        print_path(f"  {display_path(narration_path, wrap=False)}  [dim](current narration.json)[/]")
        print_path(f"  {display_path(review_path, wrap=False)}  [dim](this round's flagged issues)[/]")
        print_path(f"  {display_path(memory_path, wrap=False)}  [dim](story continuity)[/]")
        print_path(f"  {display_path(lessons_path, wrap=False)}  [dim](general lessons so far, if any)[/]")

        console.print(
            "\n[bold]It replies with three JSON blocks - overwrite each file with the matching block:[/]"
        )
        print_path(f"  {display_path(narration_path, wrap=False)}")
        print_path(f"  {display_path(memory_path, wrap=False)}")
        print_path(f"  {display_path(lessons_path, wrap=False)}")

        Prompt.ask("\n[bold]Press Enter once all three files are saved and ready[/]")

        # The next reviewer round reopens on whatever narration.json now
        # contains - if the LLM's fix didn't actually change a flagged
        # panel's text, ReviewerState pre-loads that panel's flag again so
        # it isn't silently dropped.
        if not Confirm.ask("\n[bold]Review another round before continuing to voice synthesis?[/]", default=True):
            console.print("[dim]Continuing with the current narration.json as final.[/]")
            return


def run_narration_step(project: str, chapter: str, config: RemangaConfig) -> None:
    """Generates narration.json + memory.json via the LLM copy/paste flow -
    packages whatever vision upload format is active (PDF/zip/sheets zip,
    falling back to raw sheets/panels), prints exactly what to upload and
    where to save the LLM's reply, and blocks until narration.json (and, from
    chapter 2 on, memory.json) actually has content. A no-op if narration.json
    already has real content - re-running the pipeline never re-prompts for
    an already-written chapter."""
    chap_dir = get_chapter_dir(project, chapter)
    package = config.cropper.package
    narration_path = chap_dir / "narration.json"
    panels_pdf_dir = get_panels_pdf_dir(project, chapter, create=False)
    llm_pdf_parts = sorted(panels_pdf_dir.glob("panels_*.pdf")) + sorted(panels_pdf_dir.glob("panels_*.zip")) if package.pdf_active else []
    llm_zip_parts = sorted(get_panels_zip_dir(project, chapter, create=False).glob("panels_*.zip")) if package.panels_zip_active else []
    llm_sheets_parts = sorted(get_sheets_zip_dir(project, chapter, create=False).glob("sheets_*.zip")) if package.sheets_zip_active else []
    memory_path = ensure_memory_file(project)
    memory_has_content = has_real_json_content(memory_path)
    lessons_path = ensure_global_lessons_file()
    lessons_has_content = has_real_json_content(lessons_path)
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
                p for p in get_sheets_dir(project, chapter, create=False).glob("*") if p.is_file()
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
        memory_clause = (
            " and the current memory.json (required from chapter 2 onward, for story continuity)"
            if chapter_needs_memory else
            " and the current memory.json (for story continuity)" if memory_has_content else ""
        )
        lessons_clause = " and narration_lessons.json (standing rules from past review rounds, across every project)" if lessons_has_content else ""
        console.print(
            "\n[bold]Generate narration.json + memory.json[/]\n"
            f"1. Upload any one of the file(s) listed below to your LLM, along with prompts/narration.md"
            + memory_clause + lessons_clause + ".\n"
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
        if memory_has_content:
            print_path(f"  {display_path(memory_path, wrap=False)}  [dim](story continuity)[/]")
        if lessons_has_content:
            print_path(f"  {display_path(lessons_path, wrap=False)}  [dim](standing lessons so far)[/]")

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


# Wizard-only extras: capabilities the old 7-item hardcoded menu offered that
# don't map 1:1 onto a single COMMAND_REGISTRY entry (a full chapter run
# needs its reading-direction/URL/status-overview/verify preamble around
# run_pipeline; mark-then-write is two stages stopping short of narration
# review; editing pipeline.json isn't a real CLI subcommand). Appended after
# the registry-driven list so every remanga command is still listed first.
# "Review narration only", "Compile into one video", "Change BGM and
# rebuild", and "Verify audio/video" from the old menu are now just the
# registry's own review/full-recap/remix/verify commands - no wizard-only
# wrapper needed for those anymore.
_WIZARD_EXTRAS: "list[tuple[str, Callable[[str, RemangaConfig], None]]]" = []  # filled in below, after the handlers are defined


def _prompt_param(param: Param, project: str):
    """Prompts for one Command param's value, matching its type/choices/
    default/help the way the old per-mode prompts did. `project` is only used
    for a `chapter`/`chapters` param's helper listings - the project itself is
    never prompted for here, it's already resolved by project selection."""
    if param.type == "bool":
        return Confirm.ask(f"[bold]{param.help}[/]", default=bool(param.default))
    if param.name == "chapter":
        return select_chapter(project)
    if param.name == "chapters":
        chapters = discover_chapters(project)
        if chapters:
            console.print(f"[dim]Chapters found: {', '.join(chapters)}[/]")
        raw = Prompt.ask(f"[bold]{param.help}[/]", default="").strip()
        return raw or None
    if param.type == "choice":
        return Prompt.ask(f"[bold]{param.help}[/]", choices=param.choices, default=param.default)
    default_str = "" if param.default is None else str(param.default)
    raw = Prompt.ask(f"[bold]{param.help}[/]" + (" (optional)" if not param.required else ""), default=default_str).strip()
    return raw or None


def run_interactive_pipeline():
    """Master interactive production wizard with project discovery, resume guards, and setup option."""
    console.print("[bold]remanga[/] [dim]— interactive recap production[/]\n")

    config = RemangaConfig.load()

    # 1. Project Selection / Creation / Settings
    project = select_or_create_project(config)

    # 2. Every remanga command (COMMAND_REGISTRY - the same list cli.py's
    # argparse is built from), plus a handful of wizard-only extras appended
    # after it, so this menu can never drift out of sync with what `remanga
    # <cmd> --help` actually offers.
    console.print()
    idx = 0
    for cmd in COMMAND_REGISTRY:
        idx += 1
        console.print(f"[bold]{idx}.[/] {cmd.name} [dim]— {cmd.help}[/]")
    extra_start = idx
    for label, _handler in _WIZARD_EXTRAS:
        idx += 1
        console.print(f"[bold]{idx}.[/] {label}")
    console.print()

    choices = [str(i) for i in range(1, idx + 1)]
    choice = Prompt.ask("[bold]Choose[/]", choices=choices, default="1")
    choice_idx = int(choice)

    if choice_idx <= len(COMMAND_REGISTRY):
        cmd = COMMAND_REGISTRY[choice_idx - 1]
        params: Dict[str, Any] = {}
        for param in cmd.params:
            params[param.name] = project if param.name == "project" else _prompt_param(param, project)
        cmd.handler(params, config)
    else:
        _label, handler = _WIZARD_EXTRAS[choice_idx - extra_start - 1]
        handler(project, config)


def _run_full_chapter_pipeline(project: str, config: RemangaConfig) -> None:
    """Mode 1: the full per-chapter pipeline - reading direction, MangaDex
    URL, chapter pick, voice/BGM validation, status overview, then whatever
    steps this project's pipeline.json (or the default order) lists."""
    meta = load_project_metadata(project)

    # Reading direction (right-to-left for native Japanese manga, left-to-right
    # for manhwa/manhua/webtoons and most Western comics) - asked once per
    # project and persisted to project.json, from where chapter_identity_fields
    # threads it into every panels_pdf/panels_zip/sheets_zip chapter_info.json
    # and info page/sheet. Native manga is the pipeline's overwhelming default,
    # hence "right_to_left" pre-selected.
    if "reading_direction" not in meta:
        is_rtl = Confirm.ask(
            "[bold]Is this manga read right-to-left[/] (Japanese manga convention - "
            "say no for manhwa/manhua/webtoons or Western comics)?",
            default=True,
        )
        meta["reading_direction"] = "right_to_left" if is_rtl else "left_to_right"
        save_project_metadata(project, meta)

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
    # Steps: download -> mark -> crop -> narration -> review -> tts -> mix ->
    # render, driven by this project's pipeline.json (or, absent one, today's
    # exact default order) - see pipeline.py. The resolved `url` above is
    # saved to project.json first so the download step's run(project,
    # chapter, config) signature (no url param - uniform across every step)
    # can resolve it the same way MangaDexDownloader.download_chapter's own
    # no-url fallback already does.
    # =========================================================================
    save_project_metadata(project, {"manga_url": url})
    run_pipeline(project, chapter, config, load_pipeline(project))

    # =========================================================================
    # Optional: Verify this chapter's audio/video (real ffprobe decode
    # checks, not just exists/size - see verify.py). Off by default since
    # ffmpeg writes non-atomically and a normal successful run never leaves
    # a truncated/corrupt file - only worth turning on after a crash/kill,
    # so it's asked here rather than always run.
    # =========================================================================
    if Confirm.ask("\n[bold]Verify this chapter's audio/video now?[/] (slower - only needed after a crash/kill)", default=False):
        verify_project(project, chapters=[chapter], check_video=True)


def _run_mark_then_write(project: str, config: RemangaConfig) -> None:
    """Standalone entry that covers exactly two stages, then stops: mark (or
    re-mark) panels, then hand-write narration.json yourself in the
    Narration Writer web UI instead of the usual upload-to-an-LLM flow. No
    download before it (pages must already exist - use option 1 first if
    they don't), no crop/TTS/mix/render after it. For chapters where an LLM
    narration pass isn't wanted at all, or to go back and keep filling in a
    hand-written draft."""
    project_info = next((p for p in list_projects() if p["name"] == project), None)
    chapters = project_info["chapters"] if project_info else []

    if chapters:
        table = Table(title=f"Chapters for '{project}'", show_edge=False)
        table.add_column("#", width=4)
        table.add_column("Chapter")
        table.add_column("Status")
        for idx, ch in enumerate(chapters, start=1):
            status = get_chapter_status(project, ch)
            table.add_row(str(idx), f"Chapter {ch}", status["summary"])
        console.print(table)
        default_ch = chapters[-1]
        choice = Prompt.ask("[bold]Enter chapter number to mark/write[/]", default=str(default_ch)).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(chapters):
            chapter = chapters[int(choice) - 1]
        else:
            chapter = choice
    else:
        chapter = Prompt.ask("[bold]Enter chapter number to mark/write[/]", default="1").strip()

    chap_dir = get_chapter_dir(project, chapter)
    pages_dir = chap_dir / "pages"
    pages_count = len([p for p in pages_dir.iterdir() if p.is_file()]) if pages_dir.exists() else 0
    if pages_count == 0:
        console.print(
            f"[bold red]Chapter {chapter} has no downloaded pages yet[/] - nothing to mark. "
            "Download it first (option 1) before marking/writing."
        )
        return

    # ---- Mark or re-mark panels (crops.json) ----------------------------
    crops_path = chap_dir / "crops.json"
    if has_real_json_content(crops_path):
        remark = not Confirm.ask(
            f"\n[bold]Chapter {chapter} already has marks.[/] Keep the existing marks?",
            default=True,
        )
    else:
        remark = True  # nothing to keep - mark from scratch

    if remark:
        console.print(
            "\n[bold]Mark Panels[/]\n"
            "Opening the Panel Marker web UI. Existing marks (if any) are pre-loaded - adjust "
            f"anything, then press {'⌘S' if config.marker.auto_open_browser else 'Ctrl+S'} or "
            "click Save & Continue in the browser tab.\n"
        )
        launch_panel_marker(project, chapter, config.marker)
        console.print("[green]✓ Panels marked and crops.json saved.[/]")

    # ---- Crop (panels/ - the Narration Writer needs actual images) ------
    panels_dir = chap_dir / "panels"
    panels_count = len([p for p in panels_dir.iterdir() if p.is_file()]) if panels_dir.exists() else 0
    if remark or panels_count == 0:
        console.print("\n[bold]Cropping Panels[/]")
        cropper = CoordinateCropper(config.cropper)
        cropper.crop_chapter_from_json(project, chapter)

    # ---- Hand-write narration.json ---------------------------------------
    console.print(
        "\n[bold]Write Narration[/]\n"
        "Opening the Narration Writer web UI. Type the narration line for each panel "
        "(leave a field empty for a silent beat), then click Save.\n"
    )
    launch_and_wait_writer(project, chapter, config.writer)
    console.print(
        f"\n[green]✓ narration.json for Chapter {chapter} saved.[/] "
        "[dim]Not continuing to any other stage - re-run the wizard (option 1) when you're "
        "ready for narration review/TTS/mix/render, or come back here to keep editing.[/]"
    )


# Populated here (after the handlers above are defined) rather than as a
# module-level literal at the top of the file where _WIZARD_EXTRAS is
# declared - keeps the menu's list of labels next to run_interactive_pipeline
# while still being able to reference handlers defined further down.
_WIZARD_EXTRAS.extend([
    (
        "Process a chapter (full pipeline: download → mark → crop → narrate → review → TTS → mix → render)",
        _run_full_chapter_pipeline,
    ),
    (
        "Mark/re-mark panels, then hand-write narration yourself (no LLM, stops there)",
        _run_mark_then_write,
    ),
    (
        "Edit this project's pipeline (which steps run, and in what order)",
        edit_pipeline_steps,
    ),
])
