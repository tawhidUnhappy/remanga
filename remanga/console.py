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

console = Console()


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


def display_path(path) -> str:
    """Renders a filesystem path for terminal display, shortened and pre-wrapped
    so it holds up on any screen width instead of the raw `path.resolve()`
    Rich would otherwise hard-wrap mid-directory-name on a narrow terminal
    (paths have no spaces, so Rich's word-wrap has nowhere sensible to break).

    1. Shortened to be relative to the current working directory when
       possible - the pipeline always runs from the repo root, so this drops
       the machine-specific `/mnt/datadisk/remanga/` prefix that's long and
       tells a human nothing they don't already know from being at their own
       terminal. Falls back to the absolute path for anything outside the
       cwd tree (e.g. a reference-voice file that lives elsewhere on disk).
    2. Whatever's left is pre-wrapped at path-separator boundaries to the
       live console width, so a still-long path breaks cleanly between
       directory segments on its own multiple lines instead of splitting a
       single directory/file name in half.

    Safe to embed directly in an f-string passed to console.print/Panel -
    embedded newlines render fine in both.
    """
    p = Path(path)
    try:
        text = str(p.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
    except ValueError:
        text = str(p.resolve()).replace("\\", "/")
    return wrap_at_slashes(text)
