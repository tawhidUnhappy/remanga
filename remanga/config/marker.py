"""Panel Marker web UI settings, including its editable keyboard shortcuts -
see remanga/webui/."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ShortcutsConfig(BaseModel):
    """Panel-marker keyboard shortcuts, editable from the webui's own Shortcuts
    menu (Settings gear in the topbar -> saved via POST /api/shortcuts, which
    writes straight back into this section of config.json - see
    remanga/webui/shortcuts_store.py:persist_shortcuts). Each action maps to a list of
    key combos so more than one chord can trigger it (e.g. Delete AND
    Backspace); the frontend renders/parses these itself.

    Combo syntax (parsed client-side in remanga/webui/static/js/shortcuts.js):
    '+'-separated tokens, lowercase. 'mod' means Ctrl on Windows/Linux and Cmd
    on macOS - never hardcode 'ctrl' or 'cmd' directly so a saved binding
    still makes sense on whichever OS opens it next. The non-modifier token is
    whatever KeyboardEvent.key lowercases to (e.g. 'arrowleft', 'delete', 's').
    """
    save: List[str] = Field(default_factory=lambda: ["mod+s"])
    mark_full_page: List[str] = Field(default_factory=lambda: ["mod+f"])
    tool_draw: List[str] = Field(default_factory=lambda: ["d"])
    tool_adjust: List[str] = Field(default_factory=lambda: ["v"])
    prev_page: List[str] = Field(default_factory=lambda: ["arrowleft"])
    next_page: List[str] = Field(default_factory=lambda: ["arrowright"])
    delete_mark: List[str] = Field(default_factory=lambda: ["delete", "backspace"])
    # A bare, unmodified key on purpose - not "mod+tab" (reserved by every
    # major browser for switching tabs) or "mod+0" (reserved for resetting
    # the *browser's* page zoom). Both fire a browser-chrome action a page can
    # never preventDefault() its way out of, on every mainstream browser, so
    # either one would have been permanently dead as an actual default. A
    # bare digit has no such reservation, is easy to reach, and "0" reads
    # naturally as "reset to zero."
    reset_view: List[str] = Field(default_factory=lambda: ["0"])


class MarkerConfig(BaseModel):
    """The panel-marking web UI: where crops.json comes from now, in place of the
    old paste-from-an-LLM step. See remanga/webui/."""
    host: str = "127.0.0.1"
    port: int = 8765
    auto_open_browser: bool = True

    # MAGI v3 (https://github.com/ragavsachdeva/magi) pre-fills every page's panel
    # boxes on launch so the user only has to adjust, not draw from scratch.
    # Research/non-commercial license (ragavsachdeva/magiv3 model card) - fine for
    # personal use, but not something to redistribute commercially as-is.
    magi_enabled: bool = True
    magi_repo_id: str = "ragavsachdeva/magiv3"
    magi_model_dir: str = "checkpoints/magiv3"
    magi_panel_score_threshold: float = 0.5

    # A mark's body/handles only become draggable once it's already selected
    # (a first click selects; a second, deliberate drag on the now-selected
    # mark actually moves/resizes it) - and while the Draw tool is active,
    # every OTHER mark is frozen (not selectable or draggable at all), so
    # starting a new box that happens to overlap one never nudges it by
    # accident. The mark currently selected - i.e. the one just drawn - stays
    # adjustable in Draw mode too, and loses that status the moment a new box
    # is drawn or the selection is cleared by clicking outside the page. The
    # Adjust tool has none of these restrictions: every mark is always
    # selectable/draggable, and it can still draw new boxes too. Set False to
    # restore the old behavior where any drag immediately grabs whatever
    # mark is under the cursor, selected or not, even in Draw mode.
    click_to_select: bool = True

    shortcuts: ShortcutsConfig = Field(default_factory=ShortcutsConfig)
