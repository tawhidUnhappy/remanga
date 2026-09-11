"""One wizard session: the open project, the settings it runs on, what was
picked last - and the rule that keeps a session alive when one thing run
inside it fails."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.tui import PromptInterrupt


@dataclass
class Session:
    """The open project, and what the wizard remembers while it's open.

    `config` is the machine config narrowed to this project (see
    RemangaConfig.for_project), so every command and settings screen run
    from here reads - and saves - this manga's own settings. `chapter` is the
    chapter last picked and `last` the row last picked in each menu, so
    returning to a menu, or going on to the next command for the same
    chapter, lands on what was just used: mark, crop, package on chapter 3 is
    Enter, Enter, Enter - not finding chapter 3 in the list three times."""

    machine_config: RemangaConfig
    project: str
    config: RemangaConfig = field(init=False)
    chapter: str | None = None
    last: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.config = self.machine_config.for_project(self.project)


@contextmanager
def keep_going(what: str) -> Iterator[None]:
    """Runs one thing in the session - a command, a pipeline, a settings
    screen - so that however it ends, it ends *it*, not the session. The
    wizard carries on from the menu it was started from, project and chapter
    still selected:

    - Ctrl+C at one of its questions (PromptInterrupt) cancels it. Esc backs
      out of a menu, but can't reach a typed answer; this is how you back
      out of those.
    - A failure is reported - a network blip mid-download shouldn't cost the
      whole context. The message is escaped: errors routinely quote paths,
      and Rich reads a '[' in one as markup and silently drops it, so a
      crops.json under "Title [complete]/" was reported as under "Title /".

    Everything else passes through: Ctrl+C while work is running stops
    remanga (exit 130), and so does the Exit row / ctrl+q."""
    try:
        yield
    except PromptInterrupt:
        console.print("\n[dim]Cancelled - back to the menu.[/]")
    except Exception as error:
        console.print(f"[bold red]{_esc(what)} failed:[/] {_esc(str(error) or type(error).__name__)}")
