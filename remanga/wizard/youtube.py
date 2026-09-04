"""The YouTube-metadata step: hand this chapter's finished narration to an
LLM, get youtube.json + youtube_format.json back.

Same copy/paste shape as the narration step - here are the files, there's
the prompt, paste the reply into these paths - and a no-op once the reply is
saved, so re-running the pipeline never re-prompts for a chapter that's
already been written up.

Both halves of the reply have to land for that: the format lock
(youtube_format.json) is what makes chapter 12's title/description/thumbnail
read as the same series as chapter 3's, so a chapter whose youtube.json is
written while the project still has no lock is *not* finished - the next
chapter's LLM would design a second format from scratch. That case asks
again for the lock alone, and never rewrites the youtube.json already
sitting there."""

from __future__ import annotations

from typing import Optional

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import has_real_json_content, read_json_or
from remanga.paths import (
    ensure_memory_file, ensure_youtube_format_file, get_chapter_dir, get_youtube_format_path,
    get_youtube_path,
)
from remanga.tui import confirm
from remanga.wizard.handoff import pause, print_paths, print_section

PROMPT_FILE = "prompts/youtube_metadata.md"


def _same_chapter(written: str, chapter: str) -> bool:
    """"01" and "1" are the same chapter. A label that isn't a number at all
    (a special, an omake) compares as text instead."""
    try:
        return float(written) == float(chapter)
    except ValueError:
        return written.casefold() == str(chapter).casefold()


def _block_problem(path, expected_name: str, chapter: Optional[str] = None) -> str:
    """What's wrong with the file at `path`, as one line to show the user -
    empty when it looks like the block it should be.

    Both blocks open with `file` and `chapter` (see prompts/
    youtube_metadata.md) exactly so the two can be told apart mechanically:
    they're the same shape at a glance, and pasting each into the other's path
    is the easy mistake.

    `chapter` is checked only when the caller passes one, which means
    youtube.json and never the format lock: the lock is series-wide, and its
    `chapter` records the last chapter it was applied to - legitimately an
    older one while this chapter's reply is still being written, and
    legitimately a newer one when an early chapter gets re-run. Missing keys
    are never an error either: a reply that predates them is still perfectly
    good metadata."""
    if not has_real_json_content(path):
        return f"{expected_name} is still empty/missing"
    data = read_json_or(path, None)
    if not isinstance(data, dict):
        return f"{expected_name} isn't valid JSON - paste the whole block, braces included"
    named = str(data.get("file", "")).strip()
    if named and named != expected_name:
        return f"{expected_name} holds the {named} block - the two blocks got swapped"
    written = str(data.get("chapter", "")).strip()
    if chapter is not None and written and not _same_chapter(written, chapter):
        return f"{expected_name} was written for chapter {written}, not chapter {chapter}"
    return ""


def run_youtube_metadata_step(project: str, chapter: str, config: RemangaConfig) -> None:
    youtube_path = get_youtube_path(project, chapter)
    # Looked up rather than ensured: a chapter that turns out to have no
    # narration yet bails out below, and a step that can't run shouldn't have
    # left a placeholder in the project behind it.
    format_path = get_youtube_format_path(project)
    # "Done" means each file holds the block it should, not merely that both
    # are non-empty: two blocks pasted into each other's path read as written
    # by size alone, which is the mistake the `file` key exists to catch.
    metadata_problem = _block_problem(youtube_path, "youtube.json", chapter)
    format_problem = _block_problem(format_path, "youtube_format.json")
    if not metadata_problem and not format_problem:
        return

    narration_path = get_chapter_dir(project, chapter) / "narration.json"
    if not has_real_json_content(narration_path):
        # Returns rather than raising: this is the last step of a pipeline
        # run, so there's nothing after it to protect from running on missing
        # input, and killing the whole wizard session over publishing
        # metadata would be out of proportion to what's actually wrong.
        console.print(
            f"\n[bold yellow]Skipping YouTube metadata:[/] chapter {chapter} has no narration.json "
            "yet.\n[dim]It's what the title, description and thumbnail brief are written from - "
            "run `narration` for this chapter first.[/]"
        )
        return

    memory_path = ensure_memory_file(project)
    ensure_youtube_format_file(project)
    memory_has_content = has_real_json_content(memory_path)
    have_metadata = has_real_json_content(youtube_path)
    # A lock holding the wrong block is worse than no lock: uploading it would
    # hand the LLM a "format" that is really another chapter's metadata.
    have_format = not format_problem

    # The blank placeholder - totally empty, not `{}`, same as narration.json
    # and memory.json - so the file exists to paste into and reads as "not
    # written yet" everywhere (has_real_json_content, the status panel).
    # Never written over a youtube.json that already holds a real reply.
    if not have_metadata:
        youtube_path.parent.mkdir(parents=True, exist_ok=True)
        youtube_path.write_text("", encoding="utf-8")

    print_section("Write the YouTube title, description + thumbnail brief")
    if not metadata_problem and format_problem:
        console.print(
            f"[dim]This chapter's youtube.json is already written - {format_problem}. If you "
            "still have the LLM's reply, save its second block; otherwise run the prompt again "
            "below and keep the format block.[/]"
        )
    format_clause = (
        "2. It replies with two JSON blocks - save each into the matching path below.\n"
        if have_format else
        "2. This project has no youtube_format.json yet, so the reply designs one: the title "
        "shape, description skeleton, tags, hashtags and thumbnail style every later chapter "
        "then follows.\n"
        "3. It replies with two JSON blocks - save each into the matching path below.\n"
    )
    console.print(
        f"1. Upload the file(s) below to your LLM, along with {PROMPT_FILE}.\n"
        "[dim](narration.json carries the chapter number itself, and memory.json the series "
        "title - no need to type either in chat. Adding this chapter's panels or sheets is "
        "optional: it only sharpens the thumbnail brief.)[/]\n"
        + format_clause
    )

    console.print("[bold]Upload:[/]")
    console.print(f"  {PROMPT_FILE}  [dim](the metadata prompt)[/]")
    uploads = [(narration_path, "this chapter's finished script - what the video actually says")]
    if memory_has_content:
        uploads.append((memory_path, "story continuity, for what the audience already knows"))
    if have_format:
        uploads.append((format_path, "this series' format - the reply must follow it"))
    print_paths(uploads)

    console.print(
        "\n[bold]Save its reply into:[/] [dim](every block opens with a \"file\" key naming "
        "which of these it is, so the two can't be told apart by guesswork)[/]"
    )
    console.print('  Block 1 - [dim]"file": [/]"youtube.json"')
    print_paths([(youtube_path, "")], indent="    ")
    console.print('  Block 2 - [dim]"file": [/]"youtube_format.json"')
    print_paths([(format_path, "")], indent="    ")

    pause("Press Enter once both files are saved and ready")

    while True:
        problems = []
        for path, name, for_chapter in (
            (youtube_path, "youtube.json", chapter), (format_path, "youtube_format.json", None),
        ):
            complaint = _block_problem(path, name, for_chapter)
            if complaint:
                problems.append((path, complaint))
        if not problems:
            break
        console.print("\n[bold red]Not ready yet:[/]")
        for path, complaint in problems:
            console.print(f"  [yellow]•[/] {complaint}")
            print_paths([(path, "")], indent="    ")
        console.print(
            "[dim]Both blocks of the reply are needed - youtube_format.json is what keeps every "
            "later chapter formatted the same way as this one.[/]"
        )
        if not confirm("Check again?", default=True):
            console.print(
                "[dim]Left as-is - run `youtube` for this chapter once the reply is saved.[/]"
            )
            return

    console.print("[green]✓ YouTube title, description and thumbnail brief saved.[/]")
