"""The master interactive production wizard: project/chapter discovery followed by the
full download -> crop -> narrate -> synthesize -> mix -> render pipeline, in order -
or, in full-recap mode, compiling a whole project's chapters into one continuous video."""

from __future__ import annotations

from typing import Any, Dict, List

from rich.prompt import Confirm, Prompt

from remanga.commands import COMMAND_REGISTRY, Param
from remanga.config import RemangaConfig
from remanga.console import ask_index, console, display_path, print_path
from remanga.full_recap import discover_chapters
from remanga.json_io import has_real_json_content, read_json_or
from remanga.paths import (
    ensure_global_lessons_file, ensure_memory_file, get_chapter_dir, get_narration_review_path,
    get_panels_pdf_dir, get_panels_zip_dir, get_sheets_dir, get_sheets_zip_dir,
)
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


# Every remanga command groups into one of these categories via its own
# `category` field (see commands.py) - the wizard just reads that grouping,
# it never hardcodes which command goes where. "Pipeline" isn't a real
# category any Command carries; it's appended here as its own submenu for
# edit-pipeline (editing pipeline.json isn't a bare CLI subcommand, so it
# can't live in COMMAND_REGISTRY the way every other command does).
_PIPELINE_CATEGORY = "Pipeline"


def _group_by_category() -> "Dict[str, List]":
    groups: Dict[str, List] = {}
    for cmd in COMMAND_REGISTRY:
        groups.setdefault(cmd.category, []).append(cmd)
    groups[_PIPELINE_CATEGORY] = []  # handled specially in _run_category_menu below
    return groups


def _prompt_keep_items(project: str, chapter: str) -> str:
    """Dynamic counterpart to `select_chapter` for the `wipe` command's
    `keep` param: lists exactly what currently exists for this chapter
    (source entries + generated sheets/zip/audio/video dirs - see
    reset.wipeable_entries) with numbers, and lets the user pick which of
    them to KEEP by number instead of having to type exact names blind.
    Comma-separated names still work too (an empty pick wipes everything)."""
    from remanga import reset

    entries = reset.wipeable_entries(project, chapter)
    if not entries:
        console.print("[dim]Nothing exists yet for this chapter - nothing to wipe.[/]")
        return ""
    console.print(f"[bold]Currently on disk for Chapter {chapter}:[/]")
    for i, entry in enumerate(entries, start=1):
        kind = "dir" if entry.is_dir() else "file"
        console.print(f"  [bold]{i}.[/] {entry.name} [dim]({kind})[/]")
    raw = Prompt.ask(
        "[bold]Enter number(s) (or exact name(s)) to KEEP, comma-separated - blank wipes everything[/]",
        default="",
    ).strip()
    if not raw:
        return ""
    names: List[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit() and 1 <= int(token) <= len(entries):
            names.append(entries[int(token) - 1].name)
        else:
            names.append(token)
    return ",".join(names)


def _prompt_param(param: Param, project: str, params_so_far: Dict[str, Any]):
    """Prompts for one Command param's value, matching its type/choices/
    default/help. `project` is only used for a `chapter`/`chapters` param's
    helper listings - the project itself is never prompted for here, it's
    already resolved by project selection. `params_so_far` gives access to
    earlier params in the same command (e.g. `keep`'s dynamic listing needs
    the `chapter` value already picked earlier in the same _run_command
    loop)."""
    if param.type == "bool":
        return Confirm.ask(f"[bold]{param.help}[/]", default=bool(param.default))
    if param.name == "chapter":
        return select_chapter(project)
    if param.name == "keep" and "chapter" in params_so_far:
        return _prompt_keep_items(project, params_so_far["chapter"])
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


def _run_command(cmd, project: str, config: RemangaConfig) -> None:
    params: Dict[str, Any] = {}
    for param in cmd.params:
        params[param.name] = project if param.name == "project" else _prompt_param(param, project, params)
    cmd.handler(params, config)


def _run_category_menu(category: str, cmds: "List", project: str, config: RemangaConfig) -> None:
    """One category's submenu: its commands, plus '0' for back to main menu -
    always 0, never a numbered item that shifts depending on how many
    commands this category has. Stays in this submenu after running a
    command (so running several commands from the same category - e.g.
    mark, then crop, then write - doesn't mean re-picking the category each
    time) until '0' is chosen."""
    is_pipeline = category == _PIPELINE_CATEGORY
    while True:
        console.print(f"\n[bold]{category}[/]")
        if is_pipeline:
            console.print("[bold]1.[/] edit-pipeline [dim]— Edit this project's pipeline (which steps run, and in what order)[/]")
            total = 1
        else:
            for i, cmd in enumerate(cmds, start=1):
                console.print(f"[bold]{i}.[/] {cmd.name} [dim]— {cmd.help}[/]")
            total = len(cmds)

        choice_idx = ask_index(f"Choose ({category})", total, zero_label="Back to main menu")
        if choice_idx == 0:
            return  # back to main menu

        if is_pipeline:
            edit_pipeline_steps(project, config)
        else:
            _run_command(cmds[choice_idx - 1], project, config)


def run_interactive_pipeline():
    """Master interactive production wizard: project discovery once, then a
    simple two-level nested menu - pick a category, pick a command within
    it, run it, land back on that category's submenu (or back out to the
    main category menu, or quit). No hardcoded multi-step "modes"; chaining
    commands (e.g. mark, then write, then run) is just picking them one
    after another."""
    console.print("[bold]remanga[/] [dim]— interactive recap production[/]\n")

    config = RemangaConfig.load()

    # 1. Project Selection / Creation / Settings
    project = select_or_create_project(config)

    # 2. Category menu, grouping COMMAND_REGISTRY (the same list cli.py's
    # argparse is built from) by its own `category` field, so this can never
    # drift out of sync with what `remanga <cmd> --help` actually offers.
    groups = _group_by_category()
    categories = list(groups.keys())
    while True:
        console.print(f"\n[bold]remanga — {project}[/]")
        for i, category in enumerate(categories, start=1):
            console.print(f"[bold]{i}.[/] {category}")

        choice_idx = ask_index("Choose a category", len(categories), zero_label="Quit")
        if choice_idx == 0:
            return

        category = categories[choice_idx - 1]
        _run_category_menu(category, groups[category], project, config)

