"""The narration-generation step: hand this chapter's panels to an LLM, get
narration.json + memory.json back.

A no-op when narration.json already has real content - re-running the
pipeline never re-prompts for a chapter that's already written."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import has_real_json_content
from remanga.paths import ensure_global_lessons_file, ensure_memory_file, get_chapter_dir
from remanga.wizard.handoff import pause, print_paths, print_section, print_upload_groups
from remanga.wizard.uploads import upload_groups


def chapter_needs_memory(chapter: str) -> bool:
    """From chapter 2 onward, memory.json isn't optional - it's the only
    thing carrying story continuity (character names, prior events) forward.
    Chapter 1 is exempt (nothing to carry yet), and a chapter label that
    isn't a plain number (a special/bonus chapter) skips the check rather
    than guessing where it falls in the story."""
    try:
        return float(chapter) >= 2
    except ValueError:
        return False


def run_narration_step(project: str, chapter: str, config: RemangaConfig) -> None:
    chap_dir = get_chapter_dir(project, chapter)
    narration_path = chap_dir / "narration.json"
    if has_real_json_content(narration_path):
        return

    memory_path = ensure_memory_file(project)
    lessons_path = ensure_global_lessons_file()
    memory_has_content = has_real_json_content(memory_path)
    lessons_has_content = has_real_json_content(lessons_path)
    needs_memory = chapter_needs_memory(chapter)

    groups = upload_groups(project, chapter, config)
    if not groups:
        console.print(
            "\n[bold red]Nothing to upload:[/] no panels, sheets, or zip/PDF bundle exist for "
            "this chapter.\n[dim]Run `crop` for this chapter, or turn a packaging format on "
            "(Settings → Vision outputs) and run `package`.[/]"
        )
        raise SystemExit(1)

    narration_path.parent.mkdir(parents=True, exist_ok=True)
    narration_path.write_text("", encoding="utf-8")

    memory_clause = (
        " and the current memory.json (required from chapter 2 onward, for story continuity)"
        if needs_memory else
        " and the current memory.json (for story continuity)" if memory_has_content else ""
    )
    lessons_clause = (" and narration_lessons.json (standing rules from past review rounds, "
                      "across every project)" if lessons_has_content else "")
    print_section("Generate narration.json + memory.json")
    console.print(
        "1. Upload any one of the file(s) below to your LLM, along with prompts/narration.md"
        + memory_clause + lessons_clause + ".\n"
        "[dim](each file already carries the project/manga/chapter identity itself - no need to "
        "type it in chat)[/]\n"
        "2. It replies with two JSON blocks - save each into the matching path below.\n"
    )

    console.print("[bold]Chapter folder:[/]")
    print_paths([(chap_dir, "")])

    print_upload_groups(groups, config.cropper.package.max_mb)
    extras = []
    if memory_has_content:
        extras.append((memory_path, "story continuity"))
    if lessons_has_content:
        extras.append((lessons_path, "standing lessons so far"))
    print_paths(extras)

    console.print("\n[bold]Save its reply into:[/]")
    console.print("  narration.json")
    print_paths([(narration_path, "")], indent="    ")
    console.print("  memory.json")
    print_paths([(memory_path, "")], indent="    ")

    pause("Press Enter once both files are saved and ready")

    while needs_memory and not has_real_json_content(memory_path):
        console.print(
            "\n[bold red]memory.json is still empty/missing.[/] From chapter 2 onward this is "
            "required, not optional - it's what carries story continuity forward from the last "
            "chapter. Save the LLM's memory.json reply to:"
        )
        print_paths([(memory_path, "")])
        pause("Press Enter once memory.json is saved")
