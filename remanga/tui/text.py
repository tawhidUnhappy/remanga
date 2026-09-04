"""Free-text answers: strings, numbers, and filesystem paths.

These stay on rich.prompt.Prompt rather than this package's own raw-key
loop, deliberately. Typing a long path or a transcript sentence needs line
editing, history and paste - all of which readline already provides and a
hand-rolled character loop would have to reimplement badly.

What this module adds on top is the part Prompt has no opinion about:
validation with a real retry loop, and - for paths - offering what's
already on disk as a menu first, so the common case is picking a discovered
file rather than typing its path from memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from rich.markup import escape
from rich.prompt import Prompt

from remanga.console import console, display_path
from remanga.tui.choices import Choice
from remanga.tui.result import CANCEL
from remanga.tui.select import select


def ask_text(
    label: str,
    *,
    default: str = "",
    note: str = "",
    allow_empty: bool = True,
    validate: Optional[Callable[[str], Optional[str]]] = None,
) -> str:
    """Prompts until the answer validates. `validate` returns an error
    message to reject the answer, or None to accept it."""
    if note:
        console.print(f"[dim]{escape(note)}[/]")
    while True:
        raw = Prompt.ask(f"[bold]{escape(label)}[/]", default=default).strip()
        if not raw and not allow_empty:
            console.print("[bold red]An answer is required.[/]")
            continue
        if validate:
            error = validate(raw)
            if error:
                console.print(f"[bold red]{escape(error)}[/]")
                continue
        return raw


def ask_number(
    label: str,
    *,
    default: Optional[float] = None,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    integer: bool = False,
    note: str = "",
) -> float:
    """A number, with the range checked here rather than by whatever the
    value is later handed to - a rejected answer can be retyped in place,
    while one that fails three steps later has already cost the user the
    rest of the walkthrough."""
    bounds = ""
    if minimum is not None and maximum is not None:
        bounds = f" ({minimum:g}-{maximum:g})"
    elif minimum is not None:
        bounds = f" (min {minimum:g})"
    elif maximum is not None:
        bounds = f" (max {maximum:g})"

    def validate(raw: str) -> Optional[str]:
        try:
            value = float(raw)
        except ValueError:
            return f"Enter a number{bounds}."
        if integer and value != int(value):
            return "Enter a whole number."
        if minimum is not None and value < minimum:
            return f"Must be at least {minimum:g}."
        if maximum is not None and value > maximum:
            return f"Must be at most {maximum:g}."
        return None

    raw = ask_text(f"{label}{bounds}", default="" if default is None else f"{default:g}",
                   note=note, allow_empty=False, validate=validate)
    return int(float(raw)) if integer else float(raw)


def ask_path(
    label: str,
    *,
    current: str = "",
    candidates: Sequence[Path] = (),
    note: str = "",
    must_exist: bool = True,
    allow_none: bool = False,
    none_label: str = "None",
) -> Any:
    """Picks a file: discovered candidates first, typing second.

    Every path remanga asks for (reference voice, BGM, transcript) normally
    already exists somewhere predictable - global/voice/, global/bgm/, next
    to whatever is configured now. Listing those as a menu turns the usual
    case into one keypress, and keeps typing a path available for the file
    that lives somewhere else entirely. Returns the chosen path as a string,
    None when `allow_none` is taken, or CANCEL when backed out."""
    rows: list[Choice] = []
    current_path = Path(current).expanduser() if current else None
    seen = set()

    if current_path and current_path.is_file():
        rows.append(Choice(label=display_path(current_path, wrap=False), badge="current",
                           hint=_size_hint(current_path), value=str(current_path)))
        seen.add(current_path.resolve())

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not candidate.is_file():
            continue
        seen.add(resolved)
        rows.append(Choice(label=display_path(candidate, wrap=False), hint=_size_hint(candidate),
                           value=str(candidate)))

    rows.append(Choice(label="Enter a path…", hint="type a location anywhere on disk", value=_TYPE_IT))
    if allow_none:
        rows.append(Choice(label=none_label, value=None))

    picked = select(label, rows, note=note, default=str(current_path) if current_path else None)
    if picked is CANCEL or picked is None:
        return picked
    if picked is not _TYPE_IT:
        return picked

    def validate(raw: str) -> Optional[str]:
        if not must_exist:
            return None
        expanded = Path(raw).expanduser()
        if expanded.is_file():
            return None
        return f"File not found or not a file: {expanded}"

    return ask_text("Path", default=current, allow_empty=False,
                    validate=validate).strip().strip("'\"")


class _TypeIt:
    """Marker value for the "Enter a path…" row - a plain string would be
    indistinguishable from a real answer."""


_TYPE_IT = _TypeIt()


def _size_hint(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024.0
    return ""
