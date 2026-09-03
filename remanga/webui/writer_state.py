"""In-memory session state for one narration-writing run: the panel images
found in a chapter's panels/ folder, paired with whatever narration text the
user types for each one in the Narration Writer web UI. No Flask/HTTP here -
see writer_routes.py for the API that reads/writes this.

Mirrors reviewer_state.py's shape (a flat list of panels the UI renders one
card per), but the per-panel field IS the narration text itself, not a
review note, and finishing writes narration.json directly instead of a
separate review file.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from remanga.json_io import has_real_json_content, read_json_or

PANEL_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


class WriterState:
    """All in-memory state for one narration-writing session. One chapter at a time."""

    def __init__(self, chapter_dir: Path, chapter_num: str):
        # Absolute: Flask's send_from_directory() resolves a relative directory
        # against the app's root_path (remanga/webui/), not the process cwd.
        self.chapter_dir = chapter_dir.resolve()
        self.chapter_num = chapter_num
        self.panels_dir = self.chapter_dir / "panels"
        self.narration_path = self.chapter_dir / "narration.json"
        self.finished = threading.Event()
        self.submitted = False

        if not self.panels_dir.is_dir() or not any(self.panels_dir.glob("*")):
            raise FileNotFoundError(
                f"No cropped panels found at {self.panels_dir} - mark and crop this "
                "chapter's panels first (remanga mark / remanga crop)."
            )

        panel_ids = sorted(p.stem for p in self.panels_dir.glob("*") if p.suffix.lower() in PANEL_IMAGE_EXTS)

        # If narration.json already has real content (e.g. re-opening this UI
        # to finish/edit a draft), preload each panel's existing text instead
        # of blanking it out.
        existing_text: Dict[str, str] = {}
        if has_real_json_content(self.narration_path):
            existing = read_json_or(self.narration_path, {})
            for entry in existing.get("narration", []):
                existing_text[entry.get("panel_id")] = entry.get("text", "")

        self.texts: Dict[str, str] = {pid: existing_text.get(pid, "") for pid in panel_ids}
        self.panel_order: List[str] = panel_ids

        # Generate the empty narration.json placeholder up front (same
        # convention as the wizard's own narration.json step) so the file
        # exists on disk from the moment this UI opens, even if the user
        # closes the tab without submitting.
        if not has_real_json_content(self.narration_path):
            self.narration_path.write_text("", encoding="utf-8")

    def panel_image_filename(self, panel_id: str) -> Optional[str]:
        for ext in PANEL_IMAGE_EXTS:
            candidate = self.panels_dir / f"{panel_id}{ext}"
            if candidate.exists():
                return candidate.name
        return None

    def to_payload(self) -> Dict[str, Any]:
        panels = [
            {
                "panel_id": pid,
                "text": self.texts.get(pid, ""),
                "image": self.panel_image_filename(pid),
            }
            for pid in self.panel_order
        ]
        return {
            "chapter": self.chapter_num,
            "total_panels": len(panels),
            "panels": panels,
        }

    def set_text(self, panel_id: str, text: str) -> None:
        if panel_id in self.texts:
            self.texts[panel_id] = text or ""

    def build_narration_json(self) -> Dict[str, Any]:
        narration = [{"panel_id": pid, "text": self.texts.get(pid, "")} for pid in self.panel_order]
        return {
            "chapter": self.chapter_num,
            "total_panels": len(narration),
            "narration": narration,
        }
