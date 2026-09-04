"""Printing an LLM hand-off: exactly what to upload, and exactly where to
save what comes back.

Both LLM steps (writing narration, and the review fix pass) are the same
shape - here are files, there's the prompt, paste the reply into these
paths - so they print it the same way, from here.

Every real path goes through `print_path`, one per line, never wrapped: a
path Rich has broken across two lines stops being ctrl+click-openable in an
editor's integrated terminal, which is how most of these files actually get
opened."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence, Tuple

from remanga.console import console, display_path, print_path
from remanga.tui import ask_text
from remanga.wizard.uploads import UploadGroup


def print_section(title: str) -> None:
    console.print(f"\n[bold]{title}[/]")


def print_paths(items: Iterable[Tuple[Path, str]], indent: str = "  ") -> None:
    """Prints (path, note) pairs, one clickable path per line."""
    for path, note in items:
        suffix = f"  [dim]({note})[/]" if note else ""
        print_path(f"{indent}{display_path(path, wrap=False)}{suffix}")


def print_upload_groups(groups: Sequence[UploadGroup], max_mb: float) -> None:
    """The "upload any ONE of these" listing. Plain and complete - no
    priority pick, no "or use X instead" hedging: uploading a mix of two
    groups is what breaks the chapter-identity contract in
    prompts/narration.md."""
    console.print("\n[bold]Upload any one of:[/]")
    for group in groups:
        note = (f"split into {len(group.parts)} parts, ≤{max_mb:g}MB each - upload all parts together"
                if group.is_split else "one file")
        console.print(f"  [dim]{group.kind}, {note}:[/]")
        print_paths(((part, "") for part in group.parts), indent="    ")


def pause(message: str) -> None:
    """Blocks until the user says the files are in place. Deliberately a
    plain Enter rather than a menu - the user is switching to another
    window and back, not choosing between options."""
    ask_text(message, default="", allow_empty=True)
