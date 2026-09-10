"""In-memory state for ONE chapter being marked: the loaded pages, each
page's marks, which pages the user has touched, MAGI detection progress, and
the final crops.json assembly. No Flask/HTTP here - see routes.py for the API
that reads/writes this, and detection.py for what fills apply_detected() in
from a background thread.

One chapter, deliberately. A session spanning several of them is a list of
these plus a cursor - see marker_session.py - so nothing in this file has to
know whether it's the only chapter or the fourth of twenty.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from remanga.cropper.geometry import calculate_pixel_bounds, pixel_bounds_to_box_1000
from remanga.json_io import has_real_json_content, read_json

# crops.json's per-page "a person has been here" flag. What distinguishes a
# page somebody looked at and excluded from one nobody has reached yet - two
# states that are otherwise both just an empty panel list. Its absence from
# every page in a file is how a file written before this existed is
# recognised; see MarkerState._load_existing_crops.
DECIDED_KEY = "user_decided"


class MarkerState:
    """All in-memory state for one chapter's marking."""

    def __init__(self, chapter_dir: Path, chapter_num: str):
        # Absolute: Flask's send_from_directory() resolves a relative directory
        # against the app's root_path (remanga/webui/), not the process cwd.
        self.chapter_dir = chapter_dir.resolve()
        self.chapter_num = chapter_num
        self.pages_dir = self.chapter_dir / "pages"
        self.pages: list[dict[str, Any]] = []
        self.marks: dict[str, list[dict[str, Any]]] = {}
        self.touched: set = set()  # filenames the user has edited - MAGI won't overwrite these
        self.detect_running = False
        self.detect_done = 0
        self.detect_total = 0
        self.detect_error: str | None = None
        # Whether a detection pass has already been kicked off for this
        # chapter. In a multi-chapter session a chapter can be opened, left
        # and come back to; MAGI must run for it once, on arrival, not again
        # every time the cursor lands here (see detection.start_once).
        self.detect_started = False
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
        otherwise fill in.

        A page with panels is flagged touched, so a later MAGI pass can never
        clobber marks that were already there when the session opened.

        A page with NO panels is the hard case, and it is two different
        situations wearing the same clothes:

            "I looked at this page and it has no panels"  (a title page, an
            ad, a credits page) - a decision, which MAGI must not overturn;

            "nobody has been near this page yet" - not a decision at all,
            and the one thing MAGI exists to do.

        They used to be written identically (`is_story_page: false, panels:
        []`) and read back as the first, which meant any chapter saved before
        its detection pass finished - leaving a chapter early, or the
        background worker writing one out - froze every undetected page as
        "no panels here", permanently, with no way back short of deleting
        crops.json by hand. So the decision is now recorded explicitly:
        build_crops_json writes `user_decided: true` on the pages a person
        actually touched, and only those come back as touched.

        A file written before that field existed can't be asked, so it keeps
        the old, protective reading (every empty page counts as decided) -
        detected by the field being absent from every page, not guessed at
        per page. That way an old chapter's deliberate exclusions survive,
        and every chapter saved from now on says what it means."""
        crops_path = self.chapter_dir / "crops.json"
        if not has_real_json_content(crops_path):
            return
        try:
            crop_data = read_json(crops_path)
        except Exception:
            return

        pages_by_filename = {p["filename"]: p for p in self.pages}
        entries = crop_data.get("pages", [])
        # Whether this file is new enough to distinguish the two empty-page
        # cases at all. Checked once for the file rather than per page: a
        # page that simply wasn't decided has no field either way, so asking
        # per page would read every legacy decision as "undecided".
        records_decisions = any(DECIDED_KEY in entry for entry in entries)
        for page_entry in entries:
            filename = page_entry.get("page_filename")
            page = pages_by_filename.get(filename)
            if not page:
                continue

            panels = page_entry.get("panels") or []
            if not panels:
                self.marks[filename] = []
                # Touched only if a person actually decided this page had no
                # panels - or if the file predates that distinction, in which
                # case the old assumption is the safe one.
                if page_entry.get(DECIDED_KEY) or not records_decisions:
                    self.touched.add(filename)
                continue

            marks = []
            for i, panel in enumerate(panels, start=1):
                box = panel.get("box_1000") or panel.get("box_pixel") or panel.get("coordinates")
                if not box:
                    continue
                is_normalized = "box_1000" in panel or max(box) <= 1000
                left, top, right, bottom = calculate_pixel_bounds(
                    box, page["width"], page["height"], is_1000=is_normalized
                )
                panel_id = panel.get("panel_id")
                marks.append({
                    "id": str(panel_id) if panel_id is not None else f"loaded-{i}",
                    "x": left, "y": top, "w": right - left, "h": bottom - top,
                    "src": "manual",
                })
            if marks:
                self.marks[filename] = marks
                self.touched.add(filename)

    def set_marks(self, filename: str, marks: list[dict[str, Any]]) -> None:
        self.marks[filename] = marks
        self.touched.add(filename)

    def apply_detected(self, filename: str, boxes: list[list[float]], force: bool = False) -> None:
        """Fills in MAGI's detected boxes for a page, unless the user already
        touched that page (never clobber a manual edit with a late-arriving
        background detection).

        `force` is for the one request that names a single page: pressing Run
        with the "This page" scope is asking for this page specifically, so a
        previous "no panels here" - including one inherited from a file too
        old to say who decided it - gives way. It still cannot cost anything:
        a page that HAS marks is refused even when forced, because that is
        the case where there is something to lose."""
        if filename in self.touched and (self.marks.get(filename) or not force):
            return
        self.marks[filename] = [
            {"id": f"ai-{filename}-{i}", "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1], "src": "ai"}
            for i, b in enumerate(boxes)
        ]

    def build_crops_json(self) -> dict[str, Any]:
        """This chapter's marks in the shape the cropper reads.

        Every page carries `user_decided` when a person has actually touched
        it, which is what tells an empty page that somebody looked at and
        excluded apart from one nobody has reached yet - see
        _load_existing_crops for why writing only the outcome was not
        enough. The cropper ignores the field; it exists for the next
        session of the marker."""
        pages_out = []
        for page in self.pages:
            filename = page["filename"]
            page_marks = self.marks.get(filename, [])
            decided = filename in self.touched
            if not page_marks:
                pages_out.append({
                    "page_index": page["index"],
                    "page_filename": filename,
                    "is_story_page": False,
                    "panels": [],
                    DECIDED_KEY: decided,
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
                DECIDED_KEY: decided,
            })

        return {"chapter": str(self.chapter_num), "pages": pages_out}
