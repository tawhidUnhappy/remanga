"""Which manga links are a browser site's. extension/sites.js lists the same
hosts - the helper opens nothing else."""

from __future__ import annotations

import re

COMIX_HOSTS = ("comix.to", "comix.ws")
# (site, manga id, slug) - "https://comix.to", "mwx7e", "ghost-story-club-remake".
COMIX_TITLE = re.compile(r"^(https?://(?:www\.)?comix\.(?:to|ws))/title/([a-z0-9]+)(?:-([^/?#]*))?", re.IGNORECASE)


def handles(source: str) -> bool:
    return bool(COMIX_TITLE.match((source or "").strip()))
