"""Everything that reads or writes config.json on the user's behalf.

Replaces the old remanga/setup.py + remanga/setup_wizard.py +
remanga/paths_manager.py trio, which between them held validators, a fixed
walkthrough and a second asset editor that described the same three assets
in three different ways. The split here is by concern, and each piece is
usable on its own:

    files.py     - path validation, transcript I/O, and finding the asset
                   files already on disk
    fields.py    - get/set one config field by dotted name
    assets.py    - the voice/BGM/transcript registry, its editors, and the
                   ensure_valid_* validators the audio pipeline calls
    vision.py    - the packaging checklist, generated from PackageConfig
    presets.py   - resolution/background/language option tables
    engine.py    - TTS engine + narration language screens
    video.py     - resolution/background/GPU screens
    sections.py  - every settings area as one ordered list
    summary.py   - the settings summary table
    wizard.py    - `remanga setup-config`
    paths_ui.py  - `remanga paths`

The names every other module imports (`from remanga.settings import
ensure_valid_bgm, ...`) are re-exported below.
"""

from __future__ import annotations

from remanga.settings.assets import (
    ASSETS,
    ensure_valid_bgm,
    ensure_valid_voice,
    pick_voice,
    run_asset_menu,
)
from remanga.settings.browser import run_all_settings
from remanga.settings.fields import get_field, set_field
from remanga.settings.files import (
    AUDIO_EXTENSIONS,
    discover_files,
    is_valid_file,
)
from remanga.settings.paths_ui import run_paths_manager
from remanga.settings.schema import FieldSpec, all_fields, fields_by_section
from remanga.settings.summary import settings_summary
from remanga.settings.vision import configure_vision_outputs, package_summary
from remanga.settings.wizard import run_setup_wizard

__all__ = [
    "ASSETS",
    "AUDIO_EXTENSIONS",
    "FieldSpec",
    "all_fields",
    "configure_vision_outputs",
    "discover_files",
    "ensure_valid_bgm",
    "ensure_valid_voice",
    "fields_by_section",
    "get_field",
    "is_valid_file",
    "package_summary",
    "pick_voice",
    "run_all_settings",
    "run_asset_menu",
    "run_paths_manager",
    "run_setup_wizard",
    "set_field",
    "settings_summary",
]
