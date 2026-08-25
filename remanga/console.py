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

from rich.console import Console

console = Console()
