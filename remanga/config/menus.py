"""The terminal menus - see remanga/ui/look.py."""

from __future__ import annotations

from typing import Literal

from remanga.config.base import ConfigModel


class MenusConfig(ConfigModel):
    # "android-dark" / "android-light": the Android 17 look (Material 3
    # Expressive), the same palette as the web pages' default look.
    # "terminal": Textual's own dark colours with outlined boxes, as before.
    look: Literal["android-dark", "android-light", "terminal"] = "android-dark"
