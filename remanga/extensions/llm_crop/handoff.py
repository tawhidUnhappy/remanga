"""The LLM crop hand-off: gridded pages out to Gemini, its crops back in as
crops.json.

The same shape as the narration step (remanga/wizard/narration.py) - here
are the files, there's the prompt, paste the reply into this path - printed
by the same helpers. Then the reply is checked the moment Enter is pressed,
and a reply that doesn't check out comes with a fix request to paste back
into the same Gemini conversation, waiting again, rather than failing the
step."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.extensions.llm_crop.bundles import build_grid_bundles, ensure_reply_file, grid_built
from remanga.extensions.llm_crop.config import LLMCropConfig
from remanga.extensions.llm_crop.paths import (
    PROMPT_PATH,
    get_grid_pages_dir,
    get_grid_pdf_dir,
    get_grid_zip_dir,
    get_llm_crops_path,
)
from remanga.extensions.llm_crop.reply_import import import_llm_crops
from remanga.json_io import has_real_json_content
from remanga.settings.project_prefs import cropper_config_for
from remanga.tui import is_interactive
from remanga.wizard.handoff import pause, print_paths, print_section, print_upload_groups
from remanga.wizard.uploads import UploadGroup, files_in


def llm_config(config: RemangaConfig) -> LLMCropConfig:
    """This extension's settings, as the (project-scoped) config holds them."""
    return config.extensions.llm_crop


def grid_upload_groups(project: str, chapter: str, llm: LLMCropConfig) -> list[UploadGroup]:
    """The gridded-page archives this chapter has - the grid zip, then the
    grid PDF. The grid_pages folder isn't a group: it is a directory of
    images, which the hand-off names as a folder rather than file by file."""
    groups: list[UploadGroup] = []
    if llm.zip_active:
        parts = files_in(get_grid_zip_dir(project, chapter, create=False), "grid_*.zip")
        if parts:
            groups.append(UploadGroup("grid zip", parts))
    if llm.pdf_active:
        pdf_dir = get_grid_pdf_dir(project, chapter, create=False)
        parts = files_in(pdf_dir, "grid_*.pdf") + files_in(pdf_dir, "grid_*.zip")
        if parts:
            groups.append(UploadGroup("grid PDF", parts))
    return groups


def print_llm_crop_handoff(project: str, chapter: str, config: RemangaConfig) -> None:
    """What to upload for this chapter, and where the reply goes."""
    llm = llm_config(config)
    print_section(f"Crop chapter {chapter} with Gemini")
    console.print(
        "1. Upload the prompt and any one of the grid uploads below to Gemini.\n"
        "[dim](each upload carries the chapter's identity, reading direction, grouping and page areas - "
        "nothing to type in chat)[/]\n"
        "2. It replies with one JSON block - paste it into llm_crops.json and save.\n"
    )
    console.print("[bold]Prompt:[/]")
    print_paths([(PROMPT_PATH, "")])

    groups = grid_upload_groups(project, chapter, llm)
    if groups:
        print_upload_groups(groups, llm.max_mb)
    pages_dir = get_grid_pages_dir(project, chapter, create=False)
    if llm.grid_pages and pages_dir.exists():
        console.print(f"  [dim]{'or ' if groups else ''}the folder of grid images - upload every image in it:[/]")
        print_paths([(pages_dir, "")], indent="    ")

    console.print("\n[bold]Paste the reply into:[/]")
    print_paths([(get_llm_crops_path(project, chapter), "")])


def run_llm_crop_step(project: str, chapter: str, config: RemangaConfig, *,
                      replace_marks: bool | None = None) -> bool:
    """Builds the grid uploads if they aren't there, waits for Gemini's reply
    to be pasted, checks it, and imports it into crops.json. Returns whether
    crops.json now holds Gemini's crops.

    Away from a real terminal there is nobody to press Enter, so an empty or
    failing reply raises instead of waiting - with the path to paste into, or
    the fix request to send back."""
    llm = llm_config(config)
    if grid_built(llm, project, chapter):
        ensure_reply_file(project, chapter)
    else:
        build_grid_bundles(llm, project, chapter)
    reply = get_llm_crops_path(project, chapter)
    cropper = cropper_config_for(config, project)

    while True:
        if not has_real_json_content(reply):
            print_llm_crop_handoff(project, chapter, config)
            if not is_interactive():
                raise FileNotFoundError(
                    f"Chapter {chapter}'s llm_crops.json is still empty - paste Gemini's reply into it, "
                    f"then run this again: {reply}"
                )
            pause("Press Enter once Gemini's reply is saved in llm_crops.json")
            continue

        outcome = import_llm_crops(llm, cropper, project, chapter, replace_marks=replace_marks)
        if outcome.state == "imported":
            return True
        if outcome.state == "declined":
            return False
        if outcome.state == "invalid":
            print_section("Send the problems back to Gemini")
            console.print("Paste this file's text into the same Gemini conversation, then paste its new reply "
                          "over llm_crops.json:")
            print_paths([(outcome.fix_path, "fix request"), (reply, "the reply")])
            if not is_interactive():
                raise ValueError(f"Gemini's reply for chapter {chapter} didn't check out - see {outcome.fix_path}")
            pause("Press Enter once the corrected reply is saved")
