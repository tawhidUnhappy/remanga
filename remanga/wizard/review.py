"""The narration review loop: flag panels in the Narration Reviewer web UI,
hand the flags to an LLM for a fix pass, reopen, repeat until nothing's
flagged."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import has_real_json_content, read_json_or
from remanga.paths import (
    ensure_global_lessons_file, ensure_memory_file, get_chapter_dir, get_narration_review_path,
)
from remanga.tui import confirm
from remanga.webui import launch_and_wait_reviewer
from remanga.wizard.handoff import pause, print_paths, print_section


def run_narration_review_loop(project: str, chapter: str, config: RemangaConfig) -> None:
    """Opens the reviewer on this chapter's narration.json; if anything is
    flagged, walks through the LLM fix pass and offers another round. Returns
    as soon as a round comes back with nothing flagged. A no-op if
    narration.json isn't written yet - nothing to review."""
    narration_path = get_chapter_dir(project, chapter) / "narration.json"
    if not has_real_json_content(narration_path):
        return

    memory_path = ensure_memory_file(project)
    lessons_path = ensure_global_lessons_file()
    review_path = get_narration_review_path(project, chapter)

    while True:
        print_section("Review narration")
        console.print(
            "Opening the Narration Reviewer web UI. Flag any panel whose narration is wrong and "
            "note what's wrong with it, then click Approve (nothing flagged) or Submit."
        )
        launch_and_wait_reviewer(project, chapter, config.reviewer)

        review = read_json_or(review_path, {}) if has_real_json_content(review_path) else {}
        flagged = review.get("flagged_count", 0)
        if not flagged:
            console.print("[green]✓ Narration approved - no issues flagged.[/]")
            return

        console.print(
            f"\n[bold]{flagged} panel(s) flagged.[/] Send these files to your LLM for a fix pass:\n"
            "[dim](each already carries the project/manga/chapter identity - no need to type it "
            "in chat)[/]\n"
        )
        console.print("[bold]Upload:[/]")
        console.print("  prompts/narration_review.md  [dim](the fix-pass prompt)[/]")
        print_paths([
            (narration_path, "current narration.json"),
            (review_path, "this round's flagged issues"),
            (memory_path, "story continuity"),
            (lessons_path, "general lessons so far, if any"),
        ])

        console.print("\n[bold]It replies with three JSON blocks - overwrite each file with the "
                      "matching block:[/]")
        print_paths([(narration_path, ""), (memory_path, ""), (lessons_path, "")])

        pause("Press Enter once all three files are saved and ready")

        # The next round reopens on whatever narration.json now contains - if
        # the fix didn't actually change a flagged panel's text, ReviewerState
        # pre-loads that panel's flag again rather than silently dropping it.
        if not confirm("Review another round before continuing to voice synthesis?", default=True):
            console.print("[dim]Continuing with the current narration.json as final.[/]")
            return
