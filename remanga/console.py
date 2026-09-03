"""One shared Rich Console for the whole app.

Every module used to do its own `console = Console()`, which meant 20+ live
Console instances all writing to the same terminal. Rich only guards against
*one* Console having two overlapping Live regions (a Progress bar, a
`console.status()` spinner, ...) - it has no way to know a second, unrelated
Console instance is about to scribble ANSI cursor-movement codes over the
same lines. In practice that showed up as exactly the kind of glitches this
module exists to fix: a `console.status()` spinner opened (e.g. while
downloading/loading a model) while another module's `Progress` bar was still
live on screen, each redrawing over the other - garbled colors, dropped
spaces/line breaks, and what looked like "two progress bars" fighting for
the same terminal lines.

Importing this single instance everywhere means Rich's own Live-conflict
guard (`rich.errors.LiveError`) actually works, which turns any future
version of this mistake into a clear exception during development instead of
silent on-screen corruption for the end user.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

console = Console()


def ask_index(prompt: str, count: int, default: int = 1) -> int:
    """Prompts for a 1-based menu index without Rich's usual `choices=[...]`
    behavior of echoing every valid choice inline (fine for 3-4 options,
    unreadable for a menu with a dozen-plus - e.g. "[1/2/3/4/5/6/7/8/9/10/
    11/12/13/14/15/16/17/18/19/20]"). Loops on anything that isn't a valid
    in-range integer instead of letting Prompt.ask print/validate the list
    itself. Returns the chosen index (1..count)."""
    while True:
        raw = Prompt.ask(f"[bold]{prompt}[/] [dim](1-{count})[/]", default=str(default)).strip()
        if raw.isdigit() and 1 <= int(raw) <= count:
            return int(raw)
        console.print(f"[bold red]Enter a number from 1 to {count}.[/]")


def wrap_at_slashes(text: str) -> str:
    """Pre-wraps an arbitrary long, space-free string (a URL as well as a path)
    at '/' boundaries to the live console width, so it breaks between segments
    on a narrow terminal instead of Rich hard-wrapping mid-word - the same
    problem `display_path` solves for filesystem paths, minus the Path()
    interpretation that would mangle something that isn't actually a path
    (collapsing the "//" in "https://", resolving it against the cwd, ...)."""
    width = max(console.width - 4, 20)
    if len(text) <= width:
        return text

    segments = text.split("/")
    parts = [seg + "/" for seg in segments[:-1]] + [segments[-1]]
    lines, current = [], ""
    for part in parts:
        if current and len(current) + len(part) > width:
            lines.append(current)
            current = part
        else:
            current += part
    if current:
        lines.append(current)
    return "\n".join(lines)


def display_path(path, wrap: bool = True) -> str:
    """Renders a filesystem path for terminal display, shortened - and, unless
    `wrap=False`, pre-wrapped - so it holds up on any screen width instead of
    the raw `path.resolve()` Rich would otherwise hard-wrap mid-directory-name
    on a narrow terminal (paths have no spaces, so Rich's word-wrap has
    nowhere sensible to break).

    Always: shortened to be relative to the current working directory when
    possible - the pipeline always runs from the repo root, so this drops the
    machine-specific `/mnt/datadisk/remanga/` prefix that's long and tells a
    human nothing they don't already know from being at their own terminal.
    Falls back to the absolute path for anything outside the cwd tree (e.g. a
    reference-voice file that lives elsewhere on disk).

    wrap=True (default): also pre-wrapped at path-separator boundaries to the
    live console width, so a still-long path breaks cleanly between directory
    segments across multiple lines instead of splitting a name in half. Safe
    to embed in prose passed to console.print/Panel - embedded newlines
    render fine in both.

    wrap=False: returned as one unbroken line, however long. Use this for any
    path meant to be individually ctrl+click-opened from an editor's
    integrated terminal (VS Code, etc.) - see `print_path` below, which is
    the pairing this is meant for.

    Either way, the result is Rich-markup-escaped before it comes back: a
    literal `[` in a real filename (a manga volume/chapter directory named
    "Title [Complete]" is common) would otherwise be read by Rich as the
    start of a style tag the moment this gets embedded in a console.print
    call, silently swallowing everything after it - or raising
    rich.errors.MarkupError outright for an unrecognized/unclosed tag - and
    either way never actually showing the path. Escaping here means every
    caller gets a safe-to-embed string for free, without having to remember
    to do it themselves.
    """
    p = Path(path)
    try:
        text = str(p.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
    except ValueError:
        text = str(p.resolve()).replace("\\", "/")
    text = wrap_at_slashes(text) if wrap else text
    return escape(text)


def print_path(text: str) -> None:
    """Prints one line containing a path (built with `display_path(..., wrap=False)`)
    without Rich inserting any wrapping newline of its own - needed to keep the
    path ctrl+click-openable in an editor's integrated terminal.

    Those terminals detect a clickable file link from one continuous logical
    line; a link Rich has split across two lines with an inserted '\\n' is no
    longer recognized as a single path, even though on screen both looked
    "wrapped" the same way. `soft_wrap=True` defers wrapping entirely to the
    real terminal, which still visually wraps a too-long line the same way,
    just without breaking the underlying line - so the link keeps working."""
    console.print(text, soft_wrap=True)
