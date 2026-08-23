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

from remanga.cropper.geometry import pixel_bounds_to_box_1000


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
        for i, path in enumerate(sorted(self.pages_dir.glob("page_*.*")), start=1):
            with Image.open(path) as img:
                w, h = img.size
            self.pages.append({"index": i, "filename": path.name, "width": w, "height": h})
            self.marks.setdefault(path.name, [])

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
