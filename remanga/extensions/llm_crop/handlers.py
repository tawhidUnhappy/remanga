"""The LLM crop commands' handlers - same shape as every other handler
(handler(params, config)), so the CLI and the wizard run them identically.
Everything heavy is imported inside each handler: this module is loaded while
the command registry is still being built."""

from __future__ import annotations

from typing import Any

from remanga.config import RemangaConfig
from remanga.console import console


def _chosen_chapters(params: dict[str, Any], otherwise: str) -> list[str]:
    """--chapters when given, else every chapter the project has - empty, and
    said so, when there are none."""
    from remanga.commands.selection import split_chapters
    from remanga.full_recap import discover_chapters

    project = params["project"]
    chapters = split_chapters(params.get("chapters")) or discover_chapters(project)
    if not chapters:
        console.print(f"[yellow]Project '{project}' has no chapters yet - {otherwise}.[/]")
    return chapters


def crop_grid(params: dict[str, Any], config: RemangaConfig) -> None:
    """Builds the chapter's gridded pages for Gemini - every grid format
    switched on - and its empty llm_crops.json, then says what to upload and
    where the reply goes."""
    from remanga.extensions.llm_crop.bundles import build_grid_bundles
    from remanga.extensions.llm_crop.handoff import llm_config, print_llm_crop_handoff

    project, chapter = params["project"], params["chapter"]
    build_grid_bundles(llm_config(config), project, chapter)
    print_llm_crop_handoff(project, chapter, config)
    console.print("\n[dim]Once the reply is saved, run `llm-crop` to turn it into crops.json.[/]")


def llm_crop(params: dict[str, Any], config: RemangaConfig) -> None:
    """Gemini's crops into crops.json: builds the grid uploads first if they
    aren't there, waits for the reply, checks it - see handoff.py. `--force`
    replaces Panel Marker marks without asking; otherwise a real terminal is
    asked and anything else keeps them."""
    from remanga.extensions.llm_crop.handoff import run_llm_crop_step

    run_llm_crop_step(params["project"], params["chapter"], config,
                      replace_marks=True if params.get("force") else None)


def crop_grid_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """Builds the grid uploads for every downloaded chapter - the
    whole-project form of `crop-grid`, so a manga's zips can all go to
    Gemini at once. Chapters with no pages yet are skipped and named; a
    chapter that fails stops the run where it broke."""
    from remanga.extensions.llm_crop.bundles import build_grid_bundles, chapter_pages
    from remanga.extensions.llm_crop.handoff import llm_config

    project = params["project"]
    chapters = _chosen_chapters(params, "nothing to build")
    if not chapters:
        return
    ready = [c for c in chapters if chapter_pages(project, c)]
    empty = [c for c in chapters if c not in ready]
    if not ready:
        console.print(f"[yellow]None of the {len(chapters)} chapter(s) have downloaded pages - nothing to build.[/]")
        return

    for i, chapter in enumerate(ready, start=1):
        console.print(f"[bold cyan]({i}/{len(ready)}) Chapter {chapter}[/]")
        build_grid_bundles(llm_config(config), project, chapter)
    console.print(
        f"[bold green]✓ Grid uploads built for {len(ready)} chapter(s)[/]"
        + (f"\n[dim]No pages yet, skipped: {', '.join(empty)}[/]" if empty else "")
        + "\n[dim]Upload each chapter's grid with prompts/llm_crop.md, paste each reply into that chapter's "
          "llm_crops.json, then run `llm-crop-all`.[/]"
    )


def llm_crop_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """Imports Gemini's crops for every chapter whose llm_crops.json has a
    reply pasted in - the whole-project form of `llm-crop`, without the
    waiting: chapters still empty are named and left for later.

    Replacing Panel Marker marks is one answer for every chapter that has
    them (`--force`, or the confirmation this asks a real terminal). A reply
    that doesn't check out doesn't stop the run - its fix request is written
    and the chapter is named at the end, since the other chapters' replies
    are no less good for it."""
    from remanga.extensions.llm_crop.handoff import llm_config
    from remanga.extensions.llm_crop.paths import get_llm_crops_path
    from remanga.extensions.llm_crop.reply_import import hand_marks_in, import_llm_crops
    from remanga.json_io import has_real_json_content
    from remanga.paths import get_chapter_dir
    from remanga.settings.project_prefs import cropper_config_for
    from remanga.tui import confirm, is_interactive

    project = params["project"]
    chapters = _chosen_chapters(params, "nothing to import")
    if not chapters:
        return
    pasted = [c for c in chapters if has_real_json_content(get_llm_crops_path(project, c))]
    waiting = [c for c in chapters if c not in pasted]
    if not pasted:
        console.print("[yellow]No chapter has a reply pasted into its llm_crops.json yet - nothing to import.[/] "
                      "[dim]Run `crop-grid-all` for the uploads.[/]")
        return

    marked = [c for c in pasted if hand_marks_in(get_chapter_dir(project, c) / "crops.json")]
    replace = bool(params.get("force"))
    if marked and not replace:
        console.print(f"[yellow]{len(marked)} chapter(s) have marks from the Panel Marker:[/] {', '.join(marked)}")
        replace = is_interactive() and confirm(
            f"Replace those {len(marked)} with Gemini's crops?", default=False,
            note="crops.json is rewritten from llm_crops.json; the marks are not kept anywhere",
        ) is True

    llm, cropper = llm_config(config), cropper_config_for(config, project)
    states: dict[str, str] = {}
    for i, chapter in enumerate(pasted, start=1):
        console.print(f"[bold cyan]({i}/{len(pasted)}) Chapter {chapter}[/]")
        states[chapter] = import_llm_crops(llm, cropper, project, chapter, replace_marks=replace).state

    def named(state: str) -> list[str]:
        return [c for c, s in states.items() if s == state]

    console.print(
        f"[bold green]✓ Gemini's crops imported for {len(named('imported'))} chapter(s)[/]"
        + (f"\n[yellow]Replies with problems (fix requests written under llm_crop/):[/] "
           f"{', '.join(named('invalid'))}" if named("invalid") else "")
        + (f"\n[dim]Panel Marker marks kept: {', '.join(named('declined'))}[/]" if named("declined") else "")
        + (f"\n[dim]No reply pasted yet: {', '.join(waiting)}[/]" if waiting else "")
    )
