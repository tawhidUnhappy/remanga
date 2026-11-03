"""A settings row (label, value, what changing it does) and the wait every
row's dialog shares - the base of voice_settings.py and every engine's rows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from remanga.config import RemangaConfig

Changer = Callable[["object", RemangaConfig], Awaitable[None]]


@dataclass
class Row:
    """One settings line: what it is called, what it says now, and what
    changing it does."""

    label: str
    value: str
    change: Changer
    # One short line on what the setting does, shown beside it, and the group
    # it belongs to (shown once, on the group's first row) - so the screen
    # reads without opening every row to find out.
    help: str = ""
    group: str = ""
    # The config fields (dotted, or a dotted prefix) this row sets - how the
    # screen tells which rows a project has its own value for.
    keys: tuple[str, ...] = ()


def wait_for(screen):
    return screen.app.push_screen_wait
