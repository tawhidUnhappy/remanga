"""Persists keyboard-shortcut edits from the webui's Shortcuts menu back into
config.json. Standalone from the rest of the app's config loading because the
panel marker only ever holds config.marker (a MarkerConfig), not the full
RemangaConfig or the path it was loaded from - see routes.py's
POST /api/shortcuts, which is the only caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from remanga.json_io import read_json_or, write_json

# Same cwd-relative file remanga.config.RemangaConfig.load()/.save() already
# use by default.
CONFIG_JSON_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.example.json")


def persist_shortcuts(shortcuts: Dict[str, Any]) -> None:
    """Writes marker.shortcuts into config.json, read-merge-write style (same
    pattern as remanga.paths.save_project_metadata) so every other section is
    left untouched. If config.json doesn't exist yet - the app was running on
    config.example.json's defaults - seed it from that file first instead of
    from nothing, so materializing config.json here doesn't silently drop
    whatever settings were actually in effect."""
    seed_path = CONFIG_JSON_PATH if CONFIG_JSON_PATH.exists() else CONFIG_EXAMPLE_PATH
    data = read_json_or(seed_path, {})
    data.setdefault("marker", {})
    data["marker"]["shortcuts"] = shortcuts
    write_json(CONFIG_JSON_PATH, data)
