"""Which manga references are MangaDex's."""

from __future__ import annotations

import re

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def handles(source: str) -> bool:
    """A mangadex.org link or a bare MangaDex UUID. A title to search is
    claimed by no source, so it goes to the default one."""
    text = (source or "").strip()
    return "mangadex.org" in text.lower() or bool(UUID.match(text))
