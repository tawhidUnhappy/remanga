"""MangaDex ID/chapter resolution: title search, URL/UUID parsing, and chapter lookup."""

from __future__ import annotations

import re
import time
from typing import Any

import requests
from rich.progress import BarColumn, Progress, TextColumn

from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.full_recap.discovery import chapter_key

BASE_URL = "https://api.mangadex.org"


class MangaDexResolver:
    """Resolves a MangaDex title/chapter URL, UUID, or search query down to a chapter ID."""

    def __init__(self, config: DownloaderConfig, session: requests.Session):
        self.config = config
        self.session = session

    def request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Polite HTTP caller with automatic retry, backoff, and MangaDex rate-limit protection."""
        kwargs.setdefault("timeout", 30)
        for attempt in range(self.config.max_retries + 1):
            try:
                res = self.session.request(method, url, **kwargs)
                if res.status_code == 429:
                    wait_time = (attempt + 1) * 3
                    console.print(f"[yellow]MangaDex rate limit encountered. Waiting {wait_time}s...[/]")
                    time.sleep(wait_time)
                    continue
                res.raise_for_status()
                return res
            except Exception as e:
                if attempt == self.config.max_retries:
                    raise e
                time.sleep(self.config.retry_delay_seconds * (attempt + 1))
        raise RuntimeError(f"Request failed after retries: {url}")

    def parse_manga_id(self, identifier: str) -> str:
        """Extract MangaDex UUID from a URL (title or chapter), raw UUID, or title query."""
        raw_id = identifier.strip().strip("'\"")

        # 1. Direct Chapter URL -> retrieve parent manga ID
        chapter_match = re.search(r"chapter/([a-f0-9\-]{36})", raw_id)
        if chapter_match:
            ch_uuid = chapter_match.group(1)
            ch_res = self.request_with_retry("GET", f"{BASE_URL}/chapter/{ch_uuid}")
            for rel in ch_res.json().get("data", {}).get("relationships", []):
                if rel.get("type") == "manga":
                    return rel.get("id")

        # 2. Title URL
        title_match = re.search(r"title/([a-f0-9\-]{36})", raw_id)
        if title_match:
            return title_match.group(1)

        # 3. Raw UUID string
        uuid_match = re.search(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", raw_id, re.IGNORECASE)
        if uuid_match:
            return raw_id

        # 4. Search by title
        return self.search_manga_by_title(raw_id)

    @staticmethod
    def _pick_title(title_map: dict[str, str]) -> str:
        """MangaDex's `attributes.title` is a locale -> title map (`{"en": ..., "ja": ...}`);
        prefer English, otherwise whatever locale happens to be present."""
        return title_map.get("en") or (next(iter(title_map.values())) if title_map else "Unknown Title")

    def search_manga_by_title(self, title: str) -> str:
        """Search MangaDex for a manga title and return the top matching ID."""
        console.print(f"[cyan]Searching MangaDex for manga:[/] [bold]{_esc(title)}[/]")
        res = self.request_with_retry(
            "GET",
            f"{BASE_URL}/manga",
            params={"title": title, "limit": 5, "order[relevance]": "desc"}
        )
        data = res.json().get("data", [])
        if not data:
            raise ValueError(f"No manga found on MangaDex matching query: '{title}'")

        manga_id = data[0]["id"]
        found_title = self._pick_title(data[0].get("attributes", {}).get("title", {}))
        console.print(f"[green]Found:[/] {found_title} [dim]({manga_id})[/]")
        return manga_id

    def get_manga_info(self, manga_id: str) -> dict[str, str]:
        """Fetch the facts about a manga that remanga persists in
        project.json, in one request: its display title and its original
        language.

        Resolving an ID/URL directly (parse_manga_id's title-URL/UUID
        branches) never otherwise learns anything about the manga along the
        way - only a title *search* does - so this is what lets
        downloader/mangadex.py record a human-readable `manga_title`
        regardless of which form the user originally gave it in.

        `original_language` ("ja", "ko", "zh", ...) is what the reading
        direction is derived from (see remanga/wizard/projects.py): native
        Japanese manga reads right-to-left, Korean/Chinese webtoons
        left-to-right. It's already in this response, so asking a user which
        way their manga reads - when MangaDex has just told us - is a
        question with a known answer."""
        res = self.request_with_retry("GET", f"{BASE_URL}/manga/{manga_id}")
        attrs = res.json().get("data", {}).get("attributes", {})
        return {
            "title": self._pick_title(attrs.get("title", {})),
            "original_language": str(attrs.get("originalLanguage") or "").lower(),
        }

    def get_manga_title(self, manga_id: str) -> str:
        """Just the display title - see get_manga_info."""
        return self.get_manga_info(manga_id)["title"]

    def list_chapters(self, manga_id: str) -> list[dict[str, Any]]:
        """Fetch all chapters for a manga filtered by language with pagination and polite pacing."""
        chapters: list[dict[str, Any]] = []
        limit = 100
        offset = 0

        # refresh_per_second=4: see the note on the same param in
        # downloader/mangadex.py's Progress() - a long-running spinner/bar
        # redrawing at Rich's ~10-12.5Hz default is what a stuck-terminal-
        # after-screen-lock report traced back to; 4Hz is still smooth and
        # writes a lot less while nothing's actually draining the terminal.
        with Progress(
            TextColumn("[progress.description]{task.description}"), BarColumn(), refresh_per_second=4
        ) as progress:
            task = progress.add_task("[cyan]Fetching chapter feed...", total=None)
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
                offset += limit
                if offset >= res_data.get("total", 0):
                    break
                time.sleep(0.2)
            progress.update(task, completed=100, total=100)

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
