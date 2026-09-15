"""What the sidebar shows of a marking session - the whole project as one
tree - and what the browser is told about the session itself. Mixed into
MarkerSession.

Reads chapters not opened in this session off their crops.json, without
decoding a single image: a hundred-chapter outline must not cost an image
decode per page."""

from __future__ import annotations

from typing import Any

from remanga.json_io import has_real_json_content, read_json
from remanga.paths import get_chapter_dir
from remanga.webui.marks_file import DECIDED_KEY


class SessionOutlineMixin:
    def page_names(self, chapter_num: str) -> list[str]:
        """This chapter's page filenames, in order, WITHOUT opening any of
        them. MarkerState reads every image's real size (it has to - marks
        are in image pixels); the outline only needs names and counts, and
        paying an image decode per page for every chapter in a project just
        to draw a sidebar is how a hundred-chapter session would take a
        minute to open."""
        pages_dir = get_chapter_dir(self.project, chapter_num) / "pages"
        if not pages_dir.is_dir():
            return []
        return sorted(p.name for p in pages_dir.iterdir() if p.is_file())

    def _saved_page_facts(self, chapter_num: str) -> dict[str, tuple[int, bool]]:
        """Per page of a chapter this session hasn't opened: how many panels
        its crops.json records, and whether a person decided that. Empty for
        a chapter with no crops.json, which reads correctly as "nothing here
        and nobody has said otherwise"."""
        crops_path = get_chapter_dir(self.project, chapter_num) / "crops.json"
        if not has_real_json_content(crops_path):
            return {}
        try:
            data = read_json(crops_path)
        except Exception:
            return {}
        entries = data.get("pages", [])
        # Same legacy rule as MarkerState._load_existing_crops: a file that
        # never says who decided anything is read the old way, where every
        # entry counted as a decision.
        records_decisions = any(DECIDED_KEY in entry for entry in entries)
        facts: dict[str, tuple[int, bool]] = {}
        for page in entries:
            filename = page.get("page_filename")
            if not filename:
                continue
            panels = len(page.get("panels") or [])
            decided = bool(page.get(DECIDED_KEY)) if records_decisions else True
            facts[str(filename)] = (panels, decided)
        return facts

    def outline(self) -> list[dict[str, Any]]:
        """Every chapter, every page, and how many panels each page has -
        the whole session as one tree for the sidebar to draw.

        Live for chapters already open in this session (their in-memory
        marks, including edits not yet saved), and from crops.json for the
        rest. That distinction is why each chapter says whether it's
        `loaded`: a chapter read off disk is showing you the last saved
        state, and a viewer built to double-check things should not blur
        those two together."""
        out: list[dict[str, Any]] = []
        for index, chapter_num in enumerate(self.chapters):
            state = self._states.get(chapter_num)
            if state is not None:
                pages = [
                    {"index": page["index"], "filename": page["filename"],
                     "panels": len(state.marks.get(page["filename"], [])),
                     # An empty page somebody excluded on purpose is a
                     # finished page; an empty page nobody has reached is
                     # work left. The sidebar draws them differently because
                     # telling them apart is most of what checking a
                     # half-done chapter consists of.
                     "decided": page["filename"] in state.decided}
                    for page in state.pages
                ]
            else:
                facts = self._saved_page_facts(chapter_num)
                pages = [
                    {"index": i, "filename": name,
                     "panels": facts.get(name, (0, False))[0],
                     "decided": facts.get(name, (0, False))[1]}
                    for i, name in enumerate(self.page_names(chapter_num), start=1)
                ]
            out.append({
                "chapter": chapter_num,
                "index": index,
                "loaded": state is not None,
                "pages": pages,
                "panels": sum(page["panels"] for page in pages),
                "marked_pages": sum(1 for page in pages if page["panels"]),
                # Pages with nothing on them that nobody has decided about -
                # the work actually left in this chapter. A page MAGI has
                # filled in is not "waiting" even though no person has
                # confirmed it; the sidebar counts the same thing.
                "undecided_pages": sum(1 for page in pages
                                       if not page["decided"] and not page["panels"]),
            })
        return out

    def describe(self) -> dict[str, Any]:
        """What the browser needs to know about the session itself - which
        chapter of how many, what the others are called, and whether there's
        one after this. The chapter's own pages/marks come from the
        MarkerState alongside this (see routes.py)."""
        return {
            "project": self.project,
            "chapter": self.chapter_num,
            "chapter_index": self.index,
            "chapter_total": len(self.chapters),
            "chapters": list(self.chapters),
            "has_next": self.has_next,
            "read_only": self.read_only,
            "auto_save": self.auto_save,
        }
