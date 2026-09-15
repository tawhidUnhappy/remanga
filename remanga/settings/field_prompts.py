"""A config field asked for on its own screen line, pre-filled with the value
it has now - shared by the settings screens that walk through several."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.settings.fields import set_field
from remanga.tui import ask_number, is_cancel


def ask_field_number(config: RemangaConfig, dotted: str, title: str, *, minimum: float,
                     maximum: float, integer: bool = False, note: str = "") -> bool:
    """One numeric field, pre-filled with its current value. Returns False if
    the user backed out, so a screen asking several questions can stop at the
    first Esc instead of marching on through the rest."""
    current = config
    for part in dotted.split("."):
        current = getattr(current, part)
    value = ask_number(title, default=current, minimum=minimum, maximum=maximum,
                       integer=integer, note=note)
    if is_cancel(value):
        return False
    set_field(config, dotted, int(value) if integer else float(value))
    return True
