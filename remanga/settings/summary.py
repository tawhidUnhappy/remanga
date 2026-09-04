"""One table showing everything config.json currently says, built from the
same Section list the settings menu is - so a new setting shows up in the
summary by existing, not by someone remembering to add a row here too."""

from __future__ import annotations

from rich.markup import escape
from rich.table import Table

from remanga.config import RemangaConfig
from remanga.settings.sections import SECTIONS


def settings_summary(config: RemangaConfig) -> Table:
    table = Table(title="Production settings (config.json)", show_edge=False)
    table.add_column("Setting")
    table.add_column("Current", style="dim")
    for section in SECTIONS:
        table.add_row(section.title, escape(str(section.describe(config))))
    table.add_row("Video frame rate", f"{config.video.fps} fps")
    table.add_row("Audio sample rate", f"{config.audio.sample_rate} Hz")
    return table
