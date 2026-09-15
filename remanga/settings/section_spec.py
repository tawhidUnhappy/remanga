"""What a settings section is. Its own module, with nothing heavy in it, so an
extension can declare one without importing the section list that is loading
it (see remanga.extensions.spec)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remanga.config import RemangaConfig


@dataclass(frozen=True)
class Section:
    """A title, a function that renders the setting's *current* value, and a
    function that changes it - see remanga.settings.sections."""

    key: str
    title: str
    describe: Callable[[RemangaConfig], str]
    run: Callable[[RemangaConfig], None]
    detail: str = ""
