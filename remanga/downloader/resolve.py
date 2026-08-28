"""MangaDex ID/chapter resolution: title search, URL/UUID parsing, and chapter lookup."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List
import requests
from rich.progress import BarColumn, Progress, TextColumn

from remanga.config import DownloaderConfig
from remanga.console import console


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
    def _pick_title(title_map: Dict[str, str]) -> str:
        """MangaDex's `attributes.title` is a locale -> title map (`{"en": ..., "ja": ...}`);
        prefer English, otherwise whatever locale happens to be present."""
        return title_map.get("en") or (list(title_map.values())[0] if title_map else "Unknown Title")

    def search_manga_by_title(self, title: str) -> str:
        """Search MangaDex for a manga title and return the top matching ID."""
        console.print(f"[cyan]Searching MangaDex for manga:[/] [bold]{title}[/]")
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

    def get_manga_title(self, manga_id: str) -> str:
        """Fetch a manga's display title straight from its MangaDex ID. Resolving an
        ID/URL directly (parse_manga_id's title-URL/UUID branches) never otherwise learns
        the manga's actual title along the way - only a title *search* does - so this is
        what lets downloader/mangadex.py persist a human-readable `manga_title` in
        project.json regardless of which form the user originally gave it in."""
        res = self.request_with_retry("GET", f"{BASE_URL}/manga/{manga_id}")
        attrs = res.json().get("data", {}).get("attributes", {})
        return self._pick_title(attrs.get("title", {}))

    def list_chapters(self, manga_id: str) -> List[Dict[str, Any]]:
        """Fetch all chapters for a manga filtered by language with pagination and polite pacing."""
        chapters: List[Dict[str, Any]] = []
        limit = 100
        offset = 0

        # refresh_per_second=4: see the note on the same param in
        # downloader/mangadex.py's Progress() - a long-running spinner/bar
        # redrawing at Rich's ~10-12.5Hz default is what a stuck-terminal-
        # after-screen-lock report traced back to; 4Hz is still smooth and
        # writes a lot less while nothing's actually draining the terminal.
        with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(), refresh_per_second=4) as progress:
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

    @staticmethod
    def _match_chapter_num(target: str, candidate: str) -> bool:
        """Robustly compare chapter numbers accounting for leading zeros and decimals."""
        target_s = str(target).strip()
        cand_s = str(candidate).strip()
        if not cand_s:
            return False
        if target_s == cand_s:
            return True
        target_norm = target_s.lstrip("0") or "0"
        cand_norm = cand_s.lstrip("0") or "0"
        if target_norm == cand_norm:
            return True
        try:
            if float(target_s) == float(cand_s):
                return True
        except ValueError:
            pass
        return False

    def find_chapter_id(self, manga_id: str, chapter_num: str) -> str:
        """Locate specific chapter ID by chapter number."""
        chapters = self.list_chapters(manga_id)

        for ch in chapters:
            curr_ch = str(ch.get("attributes", {}).get("chapter", ""))
            if self._match_chapter_num(chapter_num, curr_ch):
                return ch["id"]

        raise ValueError(f"Chapter '{chapter_num}' not found for manga ID: {manga_id}")
