"""A manga's chapter feed on MangaDex: every chapter in the configured language,
paged politely, one entry kept per chapter number (the newest upload), and a
chapter's id looked up in it. Mixed into MangaDexResolver (resolve.py), which
provides request_with_retry and config."""

from __future__ import annotations

import time
from typing import Any

from remanga import activity
from remanga.chapters import chapter_key

BASE_URL = "https://api.mangadex.org"


class ChapterFeed:
    """The feed half of MangaDexResolver."""

    def list_chapters(self, manga_id: str) -> list[dict[str, Any]]:
        """Fetch all chapters for a manga filtered by language with pagination and polite pacing."""
        chapters: list[dict[str, Any]] = []
        limit = 100
        offset = 0

        with activity.progress("Fetching the chapter list from MangaDex") as bar:
            while True:
                res = self.request_with_retry(
                    "GET",
                    f"{BASE_URL}/manga/{manga_id}/feed",
                    params={
                        "translatedLanguage[]": [self.config.language],
                        "order[chapter]": "asc",
                        "limit": limit,
                        "offset": offset
                    }
                )
                res_data = res.json()
                data = res_data.get("data", [])
                if not data:
                    break
                chapters.extend(data)
                bar.update(detail=f"{len(chapters)} chapters")
                offset += limit
                if offset >= res_data.get("total", 0):
                    break
                time.sleep(0.2)
            bar.update(completed=1, total=1)

        return chapters

    # MangaDex timestamps: the moment a chapter became readable, else when
    # it was published, else when the record was created. All three come
    # back as the same ISO-8601 UTC format ("2024-05-01T12:00:00+00:00"),
    # which is why they can be compared as plain strings - same layout,
    # fixed-width fields, most significant first.
    _PUBLISHED_KEYS = ("readableAt", "publishAt", "createdAt")

    @classmethod
    def _published_at(cls, chapter: dict[str, Any]) -> str:
        attributes = chapter.get("attributes", {})
        for key in cls._PUBLISHED_KEYS:
            value = attributes.get(key)
            if value:
                return str(value)
        return ""

    @classmethod
    def latest_versions(cls, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One entry per chapter number - the most recently readable one.

        A manga's feed routinely carries the same chapter number more than
        once in the same language: two scanlation groups translated it, or
        one of them re-uploaded a fixed version. Left alone that shows up as
        a chapter listed twice in the picker, and as a download that takes
        whichever copy the API happened to return first - which is not a
        choice anyone made, and can differ between two runs of the same
        command.

        So the duplicates collapse here, newest kept. Chapter numbers are
        compared by chapter_key (leading zeros and "7" vs "7.0" are the same
        chapter), and the input order is preserved - the feed is already in
        reading order and this must not disturb it."""
        best: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for chapter in chapters:
            key = chapter_key(str(chapter.get("attributes", {}).get("chapter") or ""))
            if key not in best:
                best[key] = chapter
                order.append(key)
            elif cls._published_at(chapter) > cls._published_at(best[key]):
                best[key] = chapter
        return [best[key] for key in order]

    def chapter_ids(self, manga_id: str) -> dict[str, str]:
        """Every chapter this manga's feed lists, as chapter_key -> the id of
        its latest upload (see latest_versions). One feed fetch, however many
        chapters are then looked up in it - a bulk download resolves every
        chapter from a single call instead of paging the whole feed again
        per chapter."""
        return {
            chapter_key(str(ch.get("attributes", {}).get("chapter") or "")): ch["id"]
            for ch in self.latest_versions(self.list_chapters(manga_id))
            if ch.get("attributes", {}).get("chapter")
        }

    def find_chapter_id(self, manga_id: str, chapter_num: str,
                        ids: dict[str, str] | None = None) -> str:
        """The id of this chapter's latest upload. `ids` is a chapter_ids()
        result to look it up in; without one, the feed is fetched for it."""
        found = (ids if ids is not None else self.chapter_ids(manga_id)).get(chapter_key(chapter_num))
        if found is None:
            raise ValueError(f"Chapter '{chapter_num}' not found for manga ID: {manga_id}")
        return found
