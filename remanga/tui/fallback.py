"""Numbered-prompt versions of every menu, for terminals that can't run one.

`remanga interactive` has to keep working when stdin isn't a tty - piped
input, a CI run, an editor pane that only shows output - where reading a
single keypress would simply block forever. Every public prompt in this
package checks `keys.is_interactive()` first and routes here when the
answer is no, so the fallback is a real, tested path rather than an error
message.

The numbering convention is the one remanga has always used and the ops
notes document: 1..N for the items, and 0 for back/quit at every level,
regardless of how many items that particular menu has."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from rich.prompt import Confirm, Prompt

from remanga.console import console
from remanga.tui.choices import Choice
from remanga.tui.result import CANCEL


def _print_choices(title: str, choices: Sequence[Choice], back_label: Optional[str]) -> None:
    console.print(f"\n[bold]{_safe(title)}[/]")
    for i, choice in enumerate(choices, start=1):
        badge = f"[yellow]\\[{_safe(choice.badge)}][/] " if choice.badge else ""
        hint = f" [dim]— {_safe(choice.hint)}[/]" if choice.hint else ""
        state = "[dim](unavailable)[/] " if choice.disabled else ""
        console.print(f"  [bold]{i}.[/] {state}{badge}{_safe(choice.label)}{hint}")
    if back_label:
        console.print(f"  [dim]0.[/] {_safe(back_label)}")


def _safe(text: str) -> str:
    """Escapes Rich markup in text that came from disk or user input - the
    same reason remanga.tui.frame builds Text objects instead of markup."""
    from rich.markup import escape

    return escape(str(text))


def ask_index(prompt: str, count: int, default: int = 1, zero_label: Optional[str] = None) -> int:
    """Prompts for a 1-based index without Rich's `choices=[...]` echo,
    which is fine for three options and unreadable for twenty
    ("[1/2/3/4/5/6/7/8/...]"). Loops until the answer is an in-range
    integer. Returns 0 when `zero_label` is offered and chosen."""
    lo = 0 if zero_label else 1
    hint = f"{lo}-{count}"
    while True:
        raw = Prompt.ask(f"[bold]{_safe(prompt)}[/] [dim]({hint})[/]", default=str(default)).strip()
        if raw.isdigit() and lo <= int(raw) <= count:
            return int(raw)
        console.print(f"[bold red]Enter a number from {lo} to {count}.[/]")


def select(title: str, choices: Sequence[Choice], *, default_index: int = 0,
           back_label: Optional[str] = None, **_ignored) -> Any:
    selectable = [c for c in choices if not c.disabled]
    if not selectable:
        console.print(f"[dim]{_safe(title)}: nothing to choose from.[/]")
        return CANCEL
    _print_choices(title, selectable, back_label)
    idx = ask_index("Choose", len(selectable), default=min(default_index + 1, len(selectable)),
                    zero_label=back_label)
    if idx == 0:
        return CANCEL
    return selectable[idx - 1].value


def multiselect(title: str, choices: Sequence[Choice], *, back_label: Optional[str] = None,
                ordered: bool = False, **_ignored) -> Any:
    """Comma-separated numbers instead of space-toggling. In `ordered` mode
    the order they're typed in is the order they're returned in, which is
    how the pipeline editor gets a step sequence out of a non-tty terminal."""
    selectable = [c for c in choices if not c.disabled]
    if not selectable:
        return []
    _print_choices(title, selectable, back_label)
    preselected = [str(i) for i, c in enumerate(selectable, start=1) if c.checked]
    raw = Prompt.ask(
        "[bold]Enter number(s), comma-separated[/] [dim](0 = back, blank = keep as shown)[/]",
        default=",".join(preselected),
    ).strip()
    if raw == "0":
        return CANCEL
    if not raw:
        return [c.value for c in selectable if c.checked]

    picked: List[Any] = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit() and 1 <= int(token) <= len(selectable):
            value = selectable[int(token) - 1].value
            if value not in picked:
                picked.append(value)
    return picked


def confirm(title: str, *, default: bool = True, **_ignored) -> bool:
    return Confirm.ask(f"[bold]{_safe(title)}[/]", default=default)
