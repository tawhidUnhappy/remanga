"""Persists the panel marker's own settings - the Shortcuts menu's key
bindings, and the assist card's auto-marking switches - back into
config.json.

Standalone from the rest of the app's config loading because the panel
marker only ever holds config.marker (a MarkerConfig), not the full
RemangaConfig or the path it was loaded from. Both writers below are
read-merge-write against whatever else config.json holds, so a setting saved
from a browser tab can never drop a section the marker doesn't know about.
"""

from __future__ import annotations

from typing import Any

from remanga.json_io import read_json_or, write_json
from remanga.paths import CONFIG_EXAMPLE_PATH, CONFIG_PATH as CONFIG_JSON_PATH


def _write_marker_keys(values: dict[str, Any]) -> None:
    """Merges `values` into config.json's "marker" section (same pattern as
    remanga.paths.save_project_metadata) so every other section is left
    untouched. If config.json doesn't exist yet - the app was running on
    config.example.json's defaults - seed it from that file first instead of
    from nothing, so materializing config.json here doesn't silently drop
    whatever settings were actually in effect."""
    seed_path = CONFIG_JSON_PATH if CONFIG_JSON_PATH.exists() else CONFIG_EXAMPLE_PATH
    data = read_json_or(seed_path, {})
    data.setdefault("marker", {})
    data["marker"].update(values)
    write_json(CONFIG_JSON_PATH, data)


def persist_shortcuts(shortcuts: dict[str, Any]) -> None:
    """Writes marker.shortcuts into config.json - see POST /api/shortcuts."""
    _write_marker_keys({"shortcuts": shortcuts})


def persist_marker_settings(values: dict[str, Any]) -> None:
    """Writes the action bar's scope and switches into config.json - see
    POST /api/settings.

    Saved rather than remembered per session on purpose: auto-save and
    auto-order are a way of working, not a choice about today's manga.
    Someone who wants their panels kept in reading order wants that on the
    next project too, and having to find the switch again each time is how a
    setting ends up never being used."""
    _write_marker_keys(values)
