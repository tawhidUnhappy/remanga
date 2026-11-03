"""What a pass over a chapter's PANELS starts with, shared by the Narration
Reviewer (reviewer_state.py) and the Narration Writer (writer_state.py):
where the cropped panels are, which file each panel's image is, and the event
the browser sets when the person is done.

The Panel Marker is not one of these - it works on whole pages, with drawing
and dragging on top of them (marker_state.py)."""

from __future__ import annotations

import threading
from pathlib import Path

from remanga.narration import PANEL_IMAGE_EXTS


class PanelPassState:
    """One chapter's panels, and whether the browser has finished with them.

    `submitted` stays False when the person closes the tab without
    committing to what they did - each UI decides what committing means."""

    def __init__(self, chapter_dir: Path, chapter_num: str):
        # Absolute: Flask's send_from_directory() resolves a relative directory
        # against the app's root_path (remanga/webui/), not the process cwd.
        self.chapter_dir = chapter_dir.resolve()
        self.chapter_num = chapter_num
        self.panels_dir = self.chapter_dir / "panels"
        self.finished = threading.Event()
        self.submitted = False

    def panel_image_filename(self, panel_id: str) -> str | None:
        """The file this panel's image was cropped to, whichever format that
        was - or None when the panel has no image on disk."""
        for ext in PANEL_IMAGE_EXTS:
            candidate = self.panels_dir / f"{panel_id}{ext}"
            if candidate.exists():
                return candidate.name
        return None
