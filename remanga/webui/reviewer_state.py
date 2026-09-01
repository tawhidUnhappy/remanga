"""In-memory session state for one narration-review run: the current
narration.json's panels (each paired with its cropped panel image), any
flags/notes the user attaches to a panel, and the final narration_review.json
assembly. No Flask/HTTP here - see reviewer_routes.py for the API that
reads/writes this.

Deliberately much simpler than marker_state.py: there's no drawing/dragging
to track, just a flat list of panels the user marks ok/flagged and annotates
- so this is a plain list-editor's state, not a canvas editor's.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from remanga.json_io import has_real_json_content, read_json, read_json_or


class ReviewerState:
    """All in-memory state for one review session. One chapter at a time."""

    def __init__(self, chapter_dir: Path, chapter_num: str):
        # Absolute: Flask's send_from_directory() resolves a relative directory
        # against the app's root_path (remanga/webui/), not the process cwd.
        self.chapter_dir = chapter_dir.resolve()
        self.chapter_num = chapter_num
        self.panels_dir = self.chapter_dir / "panels"
        self.finished = threading.Event()
        self.submitted = False  # False if the user closes without flagging anything as "approved"

        narration_path = self.chapter_dir / "narration.json"
        if not has_real_json_content(narration_path):
            raise FileNotFoundError(
                f"No narration.json found at {narration_path} - write the narration script first."
            )
        narration = read_json(narration_path)
        self.chapter_label = str(narration.get("chapter", chapter_num))
        self.narration_entries: List[Dict[str, Any]] = narration.get("narration", [])

        self.round = self._next_round_number()

        # Pre-seed flags/notes from the previous round's review, if any, so a
        # panel the user already flagged doesn't silently lose its note if
        # this round's narration.json still shows the same text (the LLM
        # missed the fix) - the user can see and re-submit it instead of
        # re-typing from scratch.
        self.flags: Dict[str, Dict[str, Any]] = {}
        self._preload_previous_round()

    def _history_dir(self) -> Path:
        return self.chapter_dir / "narration_reviews"

    def _next_round_number(self) -> int:
        history = self._history_dir()
        if not history.exists():
            return 1
        existing = [p for p in history.glob("round_*.json") if p.is_file()]
        nums = []
        for p in existing:
            try:
                nums.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return (max(nums) + 1) if nums else 1

    def _preload_previous_round(self) -> None:
        history = self._history_dir()
        if not history.exists():
            return
        prev_num = self.round - 1
        prev_path = history / f"round_{prev_num}.json"
        if not prev_path.exists():
            return
        prev = read_json_or(prev_path, {})
        current_text = {e.get("panel_id"): e.get("text", "") for e in self.narration_entries}
        for entry in prev.get("flagged_panels", []):
            pid = entry.get("panel_id")
            # Only carry a flag forward if this panel's text is unchanged
            # since it was flagged - if the LLM already edited it, treat it
            # as a fresh, unreviewed line instead of pre-flagging a fix that
            # may already be correct.
            if pid and current_text.get(pid) == entry.get("text_at_flag"):
                self.flags[pid] = {"issue": entry.get("issue", ""), "tag": entry.get("tag", "")}

    def panel_image_filename(self, panel_id: str) -> Optional[str]:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = self.panels_dir / f"{panel_id}{ext}"
            if candidate.exists():
                return candidate.name
        return None

    def to_payload(self) -> Dict[str, Any]:
        panels = []
        for entry in self.narration_entries:
            pid = entry.get("panel_id")
            panels.append({
                "panel_id": pid,
                "text": entry.get("text", ""),
                "image": self.panel_image_filename(pid) if pid else None,
                "flag": self.flags.get(pid),
            })
        return {
            "chapter": self.chapter_label,
            "round": self.round,
            "total_panels": len(panels),
            "panels": panels,
        }

    def set_flag(self, panel_id: str, issue: str, tag: str = "") -> None:
        issue = (issue or "").strip()
        if not issue:
            self.flags.pop(panel_id, None)
            return
        self.flags[panel_id] = {"issue": issue, "tag": (tag or "").strip()}

    def build_review_json(self, general_note: str, approved: bool) -> Dict[str, Any]:
        current_text = {e.get("panel_id"): e.get("text", "") for e in self.narration_entries}
        flagged_panels = [
            {
                "panel_id": pid,
                "text_at_flag": current_text.get(pid, ""),
                "issue": data["issue"],
                "tag": data.get("tag", ""),
            }
            for pid, data in self.flags.items()
        ]
        return {
            "chapter": self.chapter_label,
            "round": self.round,
            "approved": approved,
            "general_note": (general_note or "").strip(),
            "flagged_count": len(flagged_panels),
            "total_panels": len(self.narration_entries),
            "flagged_panels": flagged_panels,
        }
