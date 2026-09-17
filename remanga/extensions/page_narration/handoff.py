"""The page narration hand-off: the chapter's pages out to the LLM, its page
narration back in as panels/ and narration.json - the same shape as the
narration and LLM crop hand-offs, printed by the same helpers."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.extensions.page_narration.paths import NARRATION_PROMPT_PATH, PROMPT_PATH, get_reply_path
from remanga.extensions.page_narration.reply import import_page_narration
from remanga.extensions.page_narration.upload import build_page_upload, ensure_reply_file, upload_files
from remanga.json_io import has_real_json_content
from remanga.paths import ensure_global_lessons_file, ensure_memory_file
from remanga.tui import is_interactive
from remanga.wizard.handoff import pause, print_paths, print_section, print_upload_groups
from remanga.wizard.uploads import UploadGroup


def page_settings(config: RemangaConfig):
    return config.extensions.page_narration


def upload_groups(project: str, chapter: str) -> list[UploadGroup]:
    files = upload_files(project, chapter)
    groups = []
    pdfs = [f for f in files if f.suffix == ".pdf"]
    zips = [f for f in files if f.suffix == ".zip"]
    if pdfs:
        groups.append(UploadGroup("pages PDF", pdfs))
    if zips:
        groups.append(UploadGroup("pages PDF, zipped", zips))
    return groups


def print_page_handoff(project: str, chapter: str, config: RemangaConfig) -> None:
    """What to upload for this chapter, and where the two replies go."""
    memory_path = ensure_memory_file(project)
    lessons_path = ensure_global_lessons_file()
    print_section(f"Narrate chapter {chapter} page by page")
    console.print(
        "1. Upload both prompts, any one of the pages uploads below, and memory.json"
        + (" and narration_lessons.json" if has_real_json_content(lessons_path) else "")
        + " when they have content.\n"
        "[dim](each upload carries the chapter's identity and reading direction - nothing to type in chat)[/]\n"
        "2. It replies with two JSON blocks - save each into the matching path below.\n"
    )
    console.print("[bold]Prompts:[/]")
    print_paths([(PROMPT_PATH, "the page mode"), (NARRATION_PROMPT_PATH, "the narration style it follows")])
    groups = upload_groups(project, chapter)
    if groups:
        print_upload_groups(groups, page_settings(config).max_mb)
    extras = [(path, note) for path, note in ((memory_path, "story continuity"),
                                              (lessons_path, "standing lessons so far"))
              if has_real_json_content(path)]
    if extras:
        console.print("\n[bold]And, for continuity:[/]")
        print_paths(extras)
    console.print("\n[bold]Save its reply into:[/]")
    console.print("  page_narration.json")
    print_paths([(get_reply_path(project, chapter), "")], indent="    ")
    console.print("  memory.json")
    print_paths([(memory_path, "")], indent="    ")


def run_page_narration_step(project: str, chapter: str, config: RemangaConfig, *,
                            replace: bool | None = None) -> bool:
    """Builds the pages upload if it isn't there, waits for the reply to be
    pasted, checks it, and imports it. Returns whether the chapter now has
    its page narration. Away from a real terminal, an empty or failing reply
    raises instead of waiting."""
    if upload_files(project, chapter):
        ensure_reply_file(project, chapter)
    else:
        build_page_upload(page_settings(config), project, chapter)
    reply = get_reply_path(project, chapter)

    while True:
        outcome = import_page_narration(project, chapter, replace=replace)
        if outcome.state == "imported":
            return True
        if outcome.state == "declined":
            return False
        if outcome.state == "empty":
            print_page_handoff(project, chapter, config)
            if not is_interactive():
                raise FileNotFoundError(f"Chapter {chapter}'s page_narration.json is still empty - paste the "
                                        f"LLM's reply into it, then run this again: {reply}")
            pause("Press Enter once page_narration.json (and memory.json) are saved")
            continue
        print_section("Send the problems back to the LLM")
        console.print("Paste this file's text into the same conversation, then paste its new reply over "
                      "page_narration.json:")
        print_paths([(outcome.fix_path, "fix request"), (reply, "the reply")])
        if not is_interactive():
            raise ValueError(f"The page narration for chapter {chapter} didn't check out - see {outcome.fix_path}")
        pause("Press Enter once the corrected reply is saved")
