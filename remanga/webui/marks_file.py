"""crops.json as the Panel Marker reads and writes it: the marks a chapter
opens with, and the file its marks are saved as.

The cropper reads the same file and ignores everything here that only the
marker needs - which pages a person emptied on purpose, the format marker
saying a file records that, and a structured crop's own pieces."""

from __future__ import annotations

from typing import Any

from remanga.cropper.geometry import calculate_pixel_bounds, pixel_bounds_to_box_1000
from remanga.cropper.structured import STRUCTURED_KEYS
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

# A structured crop (remanga/cropper/structured.py - what the LLM crop
# extension imports) is more than its box: the frames, text and art the
# cropper builds it from, and whichever `src` wrote it. Each such mark carries
# them under STRUCTURED_KEY, with the box it was loaded at, and gets them
# written back for as long as nobody moves or resizes it - a box changed by
# hand is a hand-drawn box from then on, whoever made it first.
STRUCTURED_KEY = "structured"


class MarksFileMixin:
    """MarkerState's crops.json side. Reads and fills in the state's
    `chapter_dir`, `chapter_num`, `pages`, `marks`, `touched` and `decided`."""

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
                mark = {
                    "id": str(panel_id) if panel_id is not None else f"loaded-{i}",
                    "x": left, "y": top, "w": right - left, "h": bottom - top,
                    # Where the mark came from, as saved. This used to be
                    # hardcoded "manual" because crops.json never recorded
                    # it - so every MAGI box came back labelled as the
                    # user's own the first time a chapter was saved and
                    # reopened (and with background auto-save, that was
                    # every chapter). A file from before `src` was written
                    # can't say, so it reads as manual.
                    "src": panel.get("src") if isinstance(panel.get("src"), str) and panel.get("src") else "manual",
                }
                if panel.get("frames"):
                    mark[STRUCTURED_KEY] = {
                        "box_1000": list(box),
                        "at": [left, top, right - left, bottom - top],
                        **{key: panel.get(key) for key in STRUCTURED_KEYS},
                    }
                marks.append(mark)
            if marks:
                self.marks[filename] = marks
                self.touched.add(filename)

    def build_crops_json(self) -> dict[str, Any]:
        """This chapter's marks in the shape the cropper reads.

        An empty page carries `user_decided` when a person emptied it on
        purpose, which is what tells a page somebody excluded apart from one
        nobody has marked yet - see set_marks for what counts as emptying
        it, and _load_existing_crops for why writing only the outcome was
        not enough. The cropper ignores both this and the format marker;
        they exist for the next session of the marker."""
        def unmoved(mark: dict[str, Any], at: list[float] | None) -> bool:
            # Within half a pixel: the browser can send a loaded box back as floats.
            return bool(at) and all(
                abs(float(mark[key]) - float(value)) < 0.5
                for key, value in zip(("x", "y", "w", "h"), at, strict=True)
            )

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
                structured = m.get(STRUCTURED_KEY)
                if structured and unmoved(m, structured.get("at")):
                    # Written back exactly as loaded - see STRUCTURED_KEY.
                    panels_out.append({"panel_id": i, "box_1000": structured["box_1000"],
                                       "src": m.get("src", "manual"),
                                       **{key: structured.get(key) for key in STRUCTURED_KEYS}})
                    continue
                bounds = (m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"])
                box_1000 = pixel_bounds_to_box_1000(bounds, page["width"], page["height"])
                # `src` is for the next session of the marker (the cropper
                # ignores it): without it an AI mark and a hand-drawn one
                # are indistinguishable once written. A structured crop
                # moved by hand is a hand-drawn box from here on.
                src = "manual" if structured else m.get("src", "manual")
                panels_out.append({"panel_id": i, "box_1000": box_1000, "src": src})

            pages_out.append({
                "page_index": page["index"],
                "page_filename": filename,
                "is_story_page": True,
                "panels": panels_out,
                DECIDED_KEY: decided,
            })

        return {"chapter": str(self.chapter_num), FORMAT_KEY: MARKS_FORMAT, "pages": pages_out}
