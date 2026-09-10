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

# crops.json's per-page "the user made this page empty on purpose" flag -
# what distinguishes a page somebody looked at and excluded from one nobody
# has marked yet, two states that are otherwise both just an empty panel
# list. See MarkerState.set_marks for what earns it.
DECIDED_KEY = "user_decided"

# Top-level: this file records the flag above. A file without it is older
# than the distinction and cannot be asked what its empty pages meant, so it
# keeps the old, protective reading. A marker on the FILE rather than
# inferring from whether any page happens to carry the flag: a chapter where
# nobody excluded anything writes no flags at all, and would otherwise look
# indistinguishable from a legacy file.
FORMAT_KEY = "marks_format"
MARKS_FORMAT = 2


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
        # Pages MAGI must not overwrite: anything with marks on it, plus any
        # page the user deliberately emptied.
        self.touched: set = set()
        # Pages the user deliberately made empty - a decision, and the only
        # thing written to crops.json as such. Strictly smaller than
        # `touched`: see set_marks for why the two can't be the same set.
        self.decided: set = set()
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
        # cases at all - see FORMAT_KEY.
        records_decisions = crop_data.get(FORMAT_KEY, 0) >= MARKS_FORMAT
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
                    self.decided.add(filename)
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
        """Stores a page's marks as the browser sent them, and works out
        whether anything actually happened.

        This is called on every autosave, and the browser autosaves the page
        you are LEAVING - so paging through a chapter to look at it posts an
        unchanged empty list for every page on the way. Treating that as an
        edit is what made simply visiting a page count as "I decided this
        page has no panels": the pages a person scrolled past came back
        excluded, and MAGI never looked at them again.

        So an empty list is only a decision when the page had something on it
        a moment ago. Emptying a page is an act; arriving at one that was
        already empty is not."""
        previous = self.marks.get(filename) or []
        self.marks[filename] = marks
        if marks:
            self.touched.add(filename)
            # It isn't an empty page any more, so it isn't a decision about
            # one either - drawing on a page you had cleared takes it back.
            self.decided.discard(filename)
        elif previous:
            # Went from marked to empty: the user cleared it on purpose.
            self.touched.add(filename)
            self.decided.add(filename)

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
        # A forced pass that fills a page the user had emptied ends that
        # decision: the page has panels now, and leaving the flag set would
        # have it written back to crops.json as "deliberately empty".
        if boxes:
            self.decided.discard(filename)
        self.marks[filename] = [
            {"id": f"ai-{filename}-{i}", "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1], "src": "ai"}
            for i, b in enumerate(boxes)
        ]

    def build_crops_json(self) -> dict[str, Any]:
        """This chapter's marks in the shape the cropper reads.

        An empty page carries `user_decided` when a person emptied it on
        purpose, which is what tells a page somebody excluded apart from one
        nobody has marked yet - see set_marks for what counts as emptying
        it, and _load_existing_crops for why writing only the outcome was
        not enough. The cropper ignores both this and the format marker;
        they exist for the next session of the marker."""
        pages_out = []
        for page in self.pages:
            filename = page["filename"]
            page_marks = self.marks.get(filename, [])
            decided = filename in self.decided
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

        return {"chapter": str(self.chapter_num), FORMAT_KEY: MARKS_FORMAT, "pages": pages_out}
