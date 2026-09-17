"""The page narration commands' handlers. Everything heavy is imported inside
each handler: this module is loaded while the command registry is built."""

from __future__ import annotations

from typing import Any

from remanga.config import RemangaConfig
from remanga.console import console


def page_upload(params: dict[str, Any], config: RemangaConfig) -> None:
    from remanga.extensions.page_narration.handoff import page_settings, print_page_handoff
    from remanga.extensions.page_narration.settings import PAGE_FORMATS
    from remanga.extensions.page_narration.upload import build_page_upload

    project, chapter = params["project"], params["chapter"]
    PAGE_FORMATS.apply(config, PAGE_FORMATS.parse(params.get("formats")))
    build_page_upload(page_settings(config), project, chapter)
    print_page_handoff(project, chapter, config)
    console.print("\n[dim]Once the reply is saved, run `page-narration` to turn it into panels and narration.[/]")


def page_narration(params: dict[str, Any], config: RemangaConfig) -> None:
    from remanga.extensions.page_narration.handoff import run_page_narration_step
    from remanga.extensions.page_narration.settings import PAGE_FORMATS

    PAGE_FORMATS.apply(config, PAGE_FORMATS.parse(params.get("formats")))
    run_page_narration_step(params["project"], params["chapter"], config,
                            replace=True if params.get("force") else None)


def page_upload_all(params: dict[str, Any], config: RemangaConfig) -> None:
    from remanga.commands.handlers.common import chosen_chapters
    from remanga.extensions.page_narration.handoff import page_settings
    from remanga.extensions.page_narration.paths import chapter_page_files
    from remanga.extensions.page_narration.settings import PAGE_FORMATS
    from remanga.extensions.page_narration.upload import build_page_upload

    project = params["project"]
    formats = PAGE_FORMATS.parse(params.get("formats"))
    chapters = chosen_chapters(params, "nothing to build")
    if not chapters:
        return
    ready = [c for c in chapters if chapter_page_files(project, c)]
    empty = [c for c in chapters if c not in ready]
    if not ready:
        console.print(f"[yellow]None of the {len(chapters)} chapter(s) have downloaded pages - nothing to build.[/]")
        return
    PAGE_FORMATS.apply(config, formats)
    for i, chapter in enumerate(ready, start=1):
        console.print(f"[bold cyan]({i}/{len(ready)}) Chapter {chapter}[/]")
        build_page_upload(page_settings(config), project, chapter)
    console.print(
        f"[bold green]✓ Pages uploads built for {len(ready)} chapter(s)[/]"
        + (f"\n[dim]No pages yet, skipped: {', '.join(empty)}[/]" if empty else "")
        + "\n[dim]Upload each chapter with prompts/page_narration.md and prompts/narration.md, paste each reply "
          "into that chapter's page_narration.json, then run `page-narration` for it.[/]"
    )
