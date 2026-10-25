"""The terminal menus - see remanga/ui/look.py."""

from __future__ import annotations

from typing import Literal

from remanga.config.base import ConfigModel


class MenusConfig(ConfigModel):
    # "android-dark" / "android-light": the Android 17 look (Material 3
    # Expressive), the same palette as the web pages' default look.
    # "terminal": Textual's own dark colours with outlined boxes, as before.
    look: Literal["android-dark", "android-light", "terminal"] = "android-dark"
    # Whether the narrator engine was picked the first time remanga opened
    # (ui/first_run.py): until then the menus ask, offering only the engines
    # this machine can run.
    engine_chosen: bool = False
