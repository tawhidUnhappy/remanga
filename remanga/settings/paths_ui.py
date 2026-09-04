"""`remanga paths` - see and change the shared asset paths without going
through the whole settings screen.

Now a thin wrapper: the asset table, its live validity check and its editors
are remanga.settings.assets, shared with the settings menu's own Assets
section. What's left here is the one thing specific to this command - also
showing the narration-lessons file, which is *not* editable by hand and
exists here only so "where does that live?" has an answer."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console, display_path
from remanga.paths import get_global_lessons_path
from remanga.settings.assets import run_asset_menu


def run_paths_manager(config: RemangaConfig) -> None:
    lessons = get_global_lessons_path()
    console.print(
        "[bold]remanga[/] [dim]— shared asset paths[/]\n"
        f"[dim]Narration lessons (written by the LLM's review fix pass, not editable here): "
        f"{display_path(lessons, wrap=False)}[/]"
    )
    run_asset_menu(config, title="Asset paths")
