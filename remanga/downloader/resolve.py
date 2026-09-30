"""MangaDex manga resolution: polite requests with retry, URL/UUID parsing, title search and
the manga's facts. The chapter feed is feed.py, mixed in."""

from __future__ import annotations

import re
import time

import requests

from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.downloader.feed import BASE_URL, ChapterFeed
from remanga.longstrip.layout import LONG_STRIP_TAG


class MangaDexResolver(ChapterFeed):
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
        direction is derived from (see remanga/workflow.py): native
        Japanese manga reads right-to-left, Korean/Chinese webtoons
        left-to-right. It's already in this response, so asking a user which
        way their manga reads - when MangaDex has just told us - is a
        question with a known answer."""
        res = self.request_with_retry("GET", f"{BASE_URL}/manga/{manga_id}")
        attrs = res.json().get("data", {}).get("attributes", {})
        titles = attrs.get("title", {})
        english = titles.get("en") or next((alt["en"] for alt in attrs.get("altTitles", []) if alt.get("en")), "")
        return {
            "title": self._pick_title(titles),
            "english_title": english,
            "original_language": str(attrs.get("originalLanguage") or "").lower(),
            # MangaDex's "Long Strip" format tag: a webtoon, read by scrolling.
            "long_strip": any(tag.get("id") == LONG_STRIP_TAG for tag in attrs.get("tags", [])),
        }

    def get_manga_title(self, manga_id: str) -> str:
        """Just the display title - see get_manga_info."""
        return self.get_manga_info(manga_id)["title"]
