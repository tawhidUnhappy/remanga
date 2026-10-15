"""comix.to's chapter list, read only as far as needed.

The list shows 20 uploads a page, newest chapter first, several groups' uploads
of each chapter - Ghost Story Club's 82 chapters are 413 uploads on 21 pages,
each page a page load. Instead of reading them all:
- its first and last pages give the newest and the oldest chapter, so the
  chapter list shows every chapter between at once (2 page loads);
- a chapter about to be downloaded is looked up: the page it should be on is
  estimated from where its number falls between the pages read so far, and
  pages are read until every upload of it is known (a chapter's uploads can
  run over onto the next page) - usually one or two;
- every page read is kept (projects/<name>/comix-uploads.json), so no page is
  read twice, and the list fills in as chapters are downloaded.
A chapter number the pages read don't show yet (a 5.5, say) appears once its
page is read; one with no upload at all is said so when it is asked for."""

from __future__ import annotations

import math
from typing import Any

from remanga.json_io import read_json_or, write_json
from remanga.paths import get_project_dir

UPLOADS_FILE = "comix-uploads.json"
ABSENT = -1  # next_page_for: the list has no such chapter


def number_of(item: dict[str, Any]) -> float:
    try:
        return float(item.get("number"))
    except (TypeError, ValueError):
        return math.nan


class ListState:
    """What has been read of one manga's list: its uploads (by id) and, per
    page read, the chapter numbers it ran from and to."""

    def __init__(self, project: str, hid: str):
        self.path = get_project_dir(project) / UPLOADS_FILE
        saved = read_json_or(self.path, {})
        same = saved.get("manga_id") == hid
        self.hid = hid
        self.items: dict[str, dict[str, Any]] = {str(c["id"]): c for c in saved.get("items", []) if same and "id" in c}
        pages = (saved.get("pages") or {}) if same else {}
        self.pages: dict[int, dict[str, float]] = {int(k): v for k, v in pages.items()}
        self.total = int(saved.get("total") or 0) if same else 0
        self.per_page = int(saved.get("per_page") or 0) if same else 0

    def save(self) -> None:
        write_json(self.path, {"manga_id": self.hid, "total": self.total, "per_page": self.per_page,
                               "pages": {str(k): v for k, v in sorted(self.pages.items())},
                               "items": list(self.items.values())})

    @property
    def last_page(self) -> int:
        return math.ceil(self.total / self.per_page) if self.total and self.per_page else 0

    def listed(self) -> list[dict[str, Any]]:
        return [c for c in self.items.values() if c.get("listed")]

    def complete(self) -> bool:
        return bool(self.total) and len(self.listed()) >= self.total

    def add_page(self, number: int, page: dict[str, Any]) -> None:
        """One list page as read: its uploads kept, and which chapters it ran
        from and to. A list that grew shifts every page, so what was known
        about the other pages goes (their uploads stay)."""
        rows = [c for c in page.get("chapters") or [] if c.get("listed")]
        total = int(page.get("list_total") or 0)
        shown = page.get("shown") or {}
        if total and total != self.total:
            self.pages = {}
            self.total = total
        if shown.get("to") and shown.get("from") and shown["to"] < (self.total or shown["to"] + 1):
            self.per_page = int(shown["to"]) - int(shown["from"]) + 1  # a full page (not the last) says the size
        elif shown.get("from") and not self.per_page and number > 1:
            self.per_page = (int(shown["from"]) - 1) // (number - 1)
        for c in rows:
            self.items[str(c["id"])] = {**self.items.get(str(c["id"]), {}), **c}
        numbers = [n for n in map(number_of, rows) if not math.isnan(n)]
        if numbers:
            self.pages[number] = {"hi": max(numbers), "lo": min(numbers)}

    def _ends(self, chapter: float, holding: list[int]) -> tuple[bool, bool]:
        """Whether the chapter's uploads are known to start on the first page
        holding it and to end on the last: that page also shows a newer (or
        older) chapter, is the list's first (or last) page, or the page before
        (or after) it was read and doesn't hold it."""
        first, last = holding[0], holding[-1]
        before, after = self.pages.get(first - 1), self.pages.get(last + 1)
        starts = self.pages[first]["hi"] > chapter or first == 1 or bool(before and before["lo"] > chapter)
        ends = (self.pages[last]["lo"] < chapter or last == self.last_page
                or bool(after and after["hi"] < chapter))
        return starts, ends

    def _holding(self, chapter: float) -> list[int]:
        return sorted(n for n, p in self.pages.items() if p["lo"] <= chapter <= p["hi"])

    def covered(self, chapter: float) -> bool:
        """Every upload of the chapter is known: the pages it is on were all
        read, and where its uploads start and end is known."""
        if self.complete():
            return True
        holding = self._holding(chapter)
        if not holding or holding != list(range(holding[0], holding[-1] + 1)):
            return False
        return all(self._ends(chapter, holding))

    def next_page_for(self, chapter: float) -> int | None:
        """The page to read next to know the chapter whole - never one read
        already; None once known, ABSENT when the list has no such chapter."""
        if self.covered(chapter):
            return None
        holding = self._holding(chapter)
        if holding:
            gap = next((n for n in range(holding[0], holding[-1]) if n not in self.pages), None)
            if gap:
                return gap
            starts, _ends = self._ends(chapter, holding)
            return holding[0] - 1 if not starts else holding[-1] + 1
        above = [n for n, p in self.pages.items() if p["lo"] > chapter]  # newer chapters: earlier pages
        below = [n for n, p in self.pages.items() if p["hi"] < chapter]
        last = self.last_page
        if not above:
            return 1 if 1 not in self.pages else ABSENT
        if not below:
            return last if last and last not in self.pages else ABSENT
        a, b = max(above), min(below)
        if b - a <= 1:
            return ABSENT
        lo_a, hi_b = self.pages[a]["lo"], self.pages[b]["hi"]
        guess = a + (lo_a - chapter) / (lo_a - hi_b) * (b - a) if lo_a != hi_b else (a + b) / 2
        return min(b - 1, max(a + 1, round(guess)))

    def placeholders(self, known: set[str]) -> list[dict[str, Any]]:
        """Every whole chapter number between the oldest and newest seen that no
        page read has shown yet - listed now, looked up when downloaded."""
        if self.complete() or not self.pages:
            return []
        numbers = [p["lo"] for p in self.pages.values()] + [p["hi"] for p in self.pages.values()]
        low, high = min(numbers), max(numbers)
        return [{"chapter": str(n), "chapter_id": "", "pages": None, "title": "", "group": "", "url": "",
                 "located": False}
                for n in range(math.ceil(low), math.floor(high) + 1)
                if str(n) not in known and not self.covered(n)]  # covered with no upload: the list has none
