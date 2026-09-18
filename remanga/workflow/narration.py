"""The two browser passes over a chapter's narration: writing it by hand, and
reviewing what an LLM wrote.

Both are optional - the normal path is the PDF, an LLM and a paste - and both
work on the same narration.json, so a chapter can be started in one and
finished in the other."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.narration import panel_files
from remanga.paths import get_narration_path


def write_narration(project: str, chapter: str, config: RemangaConfig) -> Path:
    """Opens the Narration Writer: one card per panel, you type what is said,
    and saving writes narration.json in the same shape an LLM's reply has."""
    from remanga.webui import launch_and_wait_writer

    if not panel_files(project, chapter):
        raise FileNotFoundError(f"Chapter {chapter} has no panels yet - mark them and make its PDF first.")
    path = launch_and_wait_writer(project, chapter, config.writer)
    console.print(f"[bold green]✓ Narration saved[/] [dim]{path}[/]")
    return path


def review_narration(project: str, chapter: str, config: RemangaConfig) -> Path:
    """Opens the Narration Reviewer over the pasted narration: flag the panels
    that are wrong and say why. Saving writes narration_review.json, to hand
    back to the LLM with prompts/narration_review.md."""
    from remanga.webui import launch_and_wait_reviewer

    if not get_narration_path(project, chapter).exists():
        raise FileNotFoundError(f"Chapter {chapter} has no narration to review yet.")
    path = launch_and_wait_reviewer(project, chapter, config.reviewer)
    console.print(f"[bold green]✓ Review saved[/] [dim]{path}[/]")
    return path
