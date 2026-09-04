"""In-memory session state for one panel-marking run: the loaded pages, each
page's marks, which pages the user has touched, MAGI detection progress, and
the final crops.json assembly. No Flask/HTTP here - see routes.py for the API
that reads/writes this, and detection.py for what fills apply_detected() in
from a background thread.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from remanga.cropper.geometry import calculate_pixel_bounds, pixel_bounds_to_box_1000
from remanga.json_io import has_real_json_content, read_json


class MarkerState:
    """All in-memory state for one marking session. One chapter at a time."""

    def __init__(self, chapter_dir: Path, chapter_num: str):
        # Absolute: Flask's send_from_directory() resolves a relative directory
        # against the app's root_path (remanga/webui/), not the process cwd.
        self.chapter_dir = chapter_dir.resolve()
        self.chapter_num = chapter_num
        self.pages_dir = self.chapter_dir / "pages"
        self.pages: List[Dict[str, Any]] = []
        self.marks: Dict[str, List[Dict[str, Any]]] = {}
        self.touched: set = set()  # filenames the user has edited - MAGI won't overwrite these
        self.detect_running = False
        self.detect_done = 0
        self.detect_total = 0
        self.detect_error: Optional[str] = None
        self.finished = threading.Event()
        self._load_pages()

    def _load_pages(self) -> None:
        existing_pages = sorted(p for p in self.pages_dir.iterdir() if p.is_file()) if self.pages_dir.exists() else []
        for i, path in enumerate(existing_pages, start=1):
            with Image.open(path) as img:
                w, h = img.size
            self.pages.append({"index": i, "filename": path.name, "width": w, "height": h})
            self.marks.setdefault(path.name, [])
        self._load_existing_crops()

    def _load_existing_crops(self) -> None:
        """If crops.json already has real content - e.g. a marks_only/"remark"
        restart (see remanga/reset/) deliberately kept it, or the marker is just
        being reopened on an already-marked chapter - load it as this
        session's starting marks instead of the blank slate MAGI would
        otherwise fill in. Every page that has an entry in crops.json's `pages`
        is immediately flagged touched - INCLUDING a page the user deliberately
        marked as having zero panels (is_story_page: false / an empty `panels`
        list, per build_crops_json below) - so MAGI's background detection (if
        enabled) can never clobber marks, or a deliberate "no panels here"
        decision, that were already there when the session opened. Without this,
        an explicitly-excluded page looks indistinguishable from a page that was
        simply never reached yet, and a "remark" restart's fresh MAGI pass would
        silently re-populate it with an AI-guessed panel the next time the
        marker opens - overriding a decision the user already made. A no-op
        whenever crops.json is empty/missing, which is the normal case for a
        fresh chapter - existing behavior is unchanged."""
        crops_path = self.chapter_dir / "crops.json"
        if not has_real_json_content(crops_path):
            return
        try:
            crop_data = read_json(crops_path)
        except Exception:
            return

        pages_by_filename = {p["filename"]: p for p in self.pages}
        for page_entry in crop_data.get("pages", []):
            filename = page_entry.get("page_filename")
            page = pages_by_filename.get(filename)
            if not page:
                continue

            panels = page_entry.get("panels") or []
            if not panels:
                # Explicitly marked as having no panels in a previous session -
                # preserve that as touched (see the docstring above) rather
                # than leaving it looking untouched.
                self.marks[filename] = []
                self.touched.add(filename)
                continue

            marks = []
            for i, panel in enumerate(panels, start=1):
                box = panel.get("box_1000") or panel.get("box_pixel") or panel.get("coordinates")
                if not box:
                    continue
                is_normalized = "box_1000" in panel or max(box) <= 1000
                left, top, right, bottom = calculate_pixel_bounds(box, page["width"], page["height"], is_1000=is_normalized)
                panel_id = panel.get("panel_id")
                marks.append({
                    "id": str(panel_id) if panel_id is not None else f"loaded-{i}",
                    "x": left, "y": top, "w": right - left, "h": bottom - top,
                    "src": "manual",
                })
            if marks:
                self.marks[filename] = marks
                self.touched.add(filename)

    def set_marks(self, filename: str, marks: List[Dict[str, Any]]) -> None:
        self.marks[filename] = marks
        self.touched.add(filename)

    def apply_detected(self, filename: str, boxes: List[List[float]]) -> None:
        """Fills in MAGI's detected boxes for a page, unless the user already
        touched that page (never clobber a manual edit with a late-arriving
        background detection)."""
        if filename in self.touched:
            return
        self.marks[filename] = [
            {"id": f"ai-{filename}-{i}", "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1], "src": "ai"}
            for i, b in enumerate(boxes)
        ]

    def build_crops_json(self) -> Dict[str, Any]:
        pages_out = []
        for page in self.pages:
            filename = page["filename"]
            page_marks = self.marks.get(filename, [])
            if not page_marks:
                pages_out.append({
                    "page_index": page["index"],
                    "page_filename": filename,
                    "is_story_page": False,
                    "panels": [],
                })
                continue

            panels_out = []
            for i, m in enumerate(page_marks, start=1):
                bounds = (m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"])
                box_1000 = pixel_bounds_to_box_1000(bounds, page["width"], page["height"])
                panels_out.append({"panel_id": i, "box_1000": box_1000})

            pages_out.append({
                "page_index": page["index"],
                "page_filename": filename,
                "is_story_page": True,
                "panels": panels_out,
            })

        return {"chapter": str(self.chapter_num), "pages": pages_out}
