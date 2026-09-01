"""`remanga paths`: one place to see and change every shared asset path -
reference voice WAV, BGM file, and the audio8 TTS reference transcript -
instead of hunting through config.json or the full setup-config walkthrough
for one field. All three live under global/ by default (see remanga/config/
tts.py, remanga/paths.py:get_global_lessons_path) and are read fresh at
synth time, so a change here takes effect on the next chapter processed -
no restart, no re-running setup-config end to end for one path."""

from __future__ import annotations

from pathlib import Path

from rich.prompt import Confirm, Prompt
from rich.table import Table

from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc
from remanga.paths import get_global_lessons_path
from remanga.setup import (
    ensure_valid_bgm, ensure_valid_voice_prompt, is_valid_file, read_reference_text,
    write_reference_text,
)


def _status_line(label: str, path_str: str, extra: str = "") -> str:
    valid = is_valid_file(path_str)
    state = f"[green]✓ {display_path(valid)}[/]" if valid else f"[red]✗ missing:[/] {_esc(path_str or '(not set)')}"
    return f"{label}: {state}" + (f" [dim]{extra}[/]" if extra else "")


def _print_overview(config: RemangaConfig) -> None:
    table = Table(title="remanga Asset Paths", show_edge=False)
    table.add_column("#", width=4)
    table.add_column("What")
    table.add_column("Current Path / Status")

    ref_text = read_reference_text(config.tts.audio8.reference_text_path)
    lessons_path = get_global_lessons_path()

    table.add_row("1", "Reference Voice WAV (tts.spk_audio_prompt)",
                   _status_line("", config.tts.spk_audio_prompt).lstrip(": "))
    table.add_row("2", "Background Music (audio.bgm_path)",
                   _status_line("", config.audio.bgm_path,
                                extra="enabled" if config.audio.bgm_enabled else "disabled").lstrip(": "))
    table.add_row(
        "3", "TTS Reference Transcript (tts.audio8.reference_text_path)",
        (f"[green]✓ {display_path(Path(config.tts.audio8.reference_text_path))}[/] [dim]({len(ref_text)} chars)[/]"
         if ref_text else f"[yellow]○ {_esc(config.tts.audio8.reference_text_path)} (empty)[/]")
        + ("" if config.tts.engine == "audio8-tts-0.1b" else " [dim](unused - engine is indextts-2.5)[/]"),
    )
    table.add_row(
        "4", "Global Narration Lessons (read-only here)",
        f"[dim]{display_path(lessons_path)} - edited by narration_review.md's LLM output, not here[/]",
    )
    console.print(table)


def run_paths_manager(config: RemangaConfig) -> None:
    """Interactive loop: show every shared asset path and its current
    validity in one table, edit any of them by number, repeat until the
    user exits. Nothing here touches per-project paths (narration.json,
    memory.json, ...) - those already live at fixed, predictable spots
    under projects/<name>/ and aren't something a user edits by hand."""
    console.print("[bold]remanga[/] [dim]— asset paths (voice, BGM, TTS transcript)[/]\n")

    while True:
        _print_overview(config)
        console.print(
            "\n[dim]Enter a number to edit that path, or press Enter to exit "
            "(changes are saved to config.json/the transcript file immediately, no separate save step).[/]"
        )
        choice = Prompt.ask("[bold]Edit which?[/]", default="").strip()
        if not choice:
            return

        if choice == "1":
            ensure_valid_voice_prompt(config, interactive=True)
            # ensure_valid_voice_prompt no-ops silently if the current path
            # is already valid - re-prompt explicitly here since the user
            # asked to edit it, not just verify it.
            if is_valid_file(config.tts.spk_audio_prompt):
                if Confirm.ask("Current voice WAV is valid - replace it anyway?", default=False):
                    _prompt_new_path(config, "tts.spk_audio_prompt", "reference voice WAV")
        elif choice == "2":
            if is_valid_file(config.audio.bgm_path) and config.audio.bgm_enabled:
                if Confirm.ask("Current BGM file is valid - replace it anyway?", default=False):
                    _prompt_new_path(config, "audio.bgm_path", "BGM audio file")
                    config.audio.bgm_enabled = True
                    config.save()
            else:
                ensure_valid_bgm(config, interactive=True)
        elif choice == "3":
            _edit_reference_text(config)
        elif choice == "4":
            console.print(
                "[yellow]Not editable here[/] - narration_lessons.json is written by the LLM during a "
                "review round's fix pass (prompts/narration_review.md), not hand-edited. Open it directly "
                "if you need to prune or correct an entry."
            )
        else:
            console.print(f"[red]Not a valid option:[/] {choice}")
        console.print()


def _prompt_new_path(config: RemangaConfig, dotted_field: str, label: str) -> None:
    while True:
        user_input = Prompt.ask(f"[bold]New path for {label}[/]").strip().strip("'\"")
        valid = is_valid_file(user_input, min_size=1)
        if valid:
            obj, attr = _resolve_dotted(config, dotted_field)
            setattr(obj, attr, str(valid))
            config.save()
            console.print(f"[bold green]✓ Saved:[/] {display_path(valid)}")
            return
        console.print(f"[bold red]✗ File not found or empty:[/] {Path(user_input).expanduser()}. Try again.")


def _resolve_dotted(config: RemangaConfig, dotted_field: str):
    *parents, attr = dotted_field.split(".")
    obj = config
    for name in parents:
        obj = getattr(obj, name)
    return obj, attr


def _edit_reference_text(config: RemangaConfig) -> None:
    path_str = config.tts.audio8.reference_text_path
    current = read_reference_text(path_str)
    if current:
        console.print(f"Current transcript ({_esc(path_str)}): [green]{_esc(current)}[/]")
    else:
        console.print(f"[dim]No transcript yet - will be saved to: {_esc(path_str)}[/]")
    new_text = Prompt.ask("[bold]New transcript text[/]", default=current).strip()
    saved = write_reference_text(path_str, new_text)
    console.print(f"[bold green]✓ Transcript saved to:[/] {display_path(saved)}")
