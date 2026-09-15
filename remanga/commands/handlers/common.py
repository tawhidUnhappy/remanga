"""What the whole-project handlers share."""

from __future__ import annotations

from typing import Any

from remanga.commands.selection import split_chapters
from remanga.console import console
from remanga.full_recap import discover_chapters


def chosen_chapters(params: dict[str, Any], otherwise: str) -> list[str]:
    """The chapters a whole-project command works on: --chapters when given,
    else every chapter the project has. Empty - and says so, ending with
    `otherwise` - when the project has none yet."""
    project = params["project"]
    chapters = split_chapters(params.get("chapters")) or discover_chapters(project)
    if not chapters:
        console.print(f"[yellow]Project '{project}' has no chapters yet - {otherwise}.[/]")
    return chapters
