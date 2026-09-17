"""The page-narration pipeline step - page mode's replacement for mark, crop,
package and narration."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import has_real_json_content
from remanga.narration.document import narration_path
from remanga.pipeline.spec import Step


def run_page_narration(project: str, chapter: str, config: RemangaConfig) -> None:
    """A no-op for a chapter that already has narration, like the narration
    step: re-running a pipeline never re-imports or replaces a script. The
    `page-narration` command does that on purpose."""
    if has_real_json_content(narration_path(project, chapter)):
        return
    from remanga.extensions.page_narration.handoff import run_page_narration_step

    console.print("\n[bold]Step — Narrating whole pages[/]")
    run_page_narration_step(project, chapter, config)


PAGE_NARRATION_STEP = Step(
    "page-narration",
    "Page mode: the pages go to the LLM whole, and its page-by-page narration becomes panels and narration.json",
    run_page_narration, needs=["download"],
)
