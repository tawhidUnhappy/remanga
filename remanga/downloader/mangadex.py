from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn

from remanga.config import (
    DownloaderConfig,
    get_chapter_dir,
    load_project_metadata,
    save_project_metadata,
)

console = Console()


class MangaDexDownloader:
    BASE_URL = "https://api.mangadex.org"

    def __init__(self, config: Optional[DownloaderConfig] = None):
        self.config = config or DownloaderConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "remanga-recap-pipeline/1.0"
        })

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Helper to send HTTP requests with automatic retry on rate limits or errors."""
        kwargs.setdefault("timeout", 30)
        for attempt in range(self.config.max_retries + 1):
            try:
                res = self.session.request(method, url, **kwargs)
                if res.status_code == 429:
                    wait_time = (attempt + 1) * 2
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
        """Extract MangaDex UUID from a URL (title or chapter), raw UUID, or search title."""
        raw_id = identifier.strip().strip("'\"")

        # 1. Direct Chapter URL -> query chapter metadata to obtain parent manga ID
        chapter_match = re.search(r"chapter/([a-f0-9\-]{36})", raw_id)
        if chapter_match:
            ch_uuid = chapter_match.group(1)
            ch_res = self._request_with_retry("GET", f"{self.BASE_URL}/chapter/{ch_uuid}")
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

    def search_manga_by_title(self, title: str) -> str:
        """Search MangaDex for a manga title and return the top matching ID."""
        console.print(f"[cyan]Searching MangaDex for manga:[/] [bold]{title}[/]")
        res = self._request_with_retry(
            "GET",
            f"{self.BASE_URL}/manga",
            params={"title": title, "limit": 5, "order[relevance]": "desc"}
        )
        data = res.json().get("data", [])
        if not data:
            raise ValueError(f"No manga found on MangaDex matching query: '{title}'")

        manga_id = data[0]["id"]
        attrs = data[0].get("attributes", {})
        title_map = attrs.get("title", {})
        found_title = title_map.get("en") or (list(title_map.values())[0] if title_map else "Unknown Title")
        console.print(f"[green]Found:[/] {found_title} [dim]({manga_id})[/]")
        return manga_id

    def list_chapters(self, manga_id: str) -> List[Dict[str, Any]]:
        """Fetch all chapters for a manga filtered by language with pagination."""
        chapters: List[Dict[str, Any]] = []
        limit = 100
        offset = 0

        with Progress(TextColumn("[progress.description]{task.description}"), BarColumn()) as progress:
            task = progress.add_task("[cyan]Fetching chapter feed...", total=None)
            while True:
                res = self._request_with_retry(
                    "GET",
                    f"{self.BASE_URL}/manga/{manga_id}/feed",
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
                time.sleep(0.1)
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

    def download_chapter(self, manga_id_or_url: Optional[str], chapter_num: str, project_name: str) -> Path:
        """Download high-resolution chapter images into project directory and save URL metadata."""
        # Check saved URL if not provided
        if not manga_id_or_url:
            meta = load_project_metadata(project_name)
            manga_id_or_url = meta.get("manga_url") or meta.get("manga_id")
            if not manga_id_or_url:
                raise ValueError(
                    f"No MangaDex URL or ID provided and none found saved for project '{project_name}'."
                )

        manga_id = self.parse_manga_id(manga_id_or_url)

        # Save project metadata for reuse across chapters
        save_project_metadata(project_name, {
            "project_name": project_name,
            "manga_url": manga_id_or_url,
            "manga_id": manga_id,
            "last_chapter": str(chapter_num)
        })

        chapter_id = self.find_chapter_id(manga_id, chapter_num)

        dest_dir = get_chapter_dir(project_name, chapter_num) / "pages"
        dest_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"[cyan]Retrieving MangaDex node for chapter {chapter_num}...[/]")
        at_home_res = self._request_with_retry("GET", f"{self.BASE_URL}/at-home/server/{chapter_id}")
        server_info = at_home_res.json()

        base_url = server_info["baseUrl"]
        chapter_data = server_info["chapter"]
        hash_code = chapter_data["hash"]
        quality_key = self.config.image_quality
        filenames = chapter_data[quality_key]

        console.print(f"[green]Downloading {len(filenames)} pages to:[/] {dest_dir}")

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TimeRemainingColumn()
        ) as progress:
            dl_task = progress.add_task("[yellow]Downloading pages...", total=len(filenames))

            for idx, filename in enumerate(filenames, start=1):
                page_ext = Path(filename).suffix or ".png"
                out_path = dest_dir / f"page_{idx:03d}{page_ext}"

                if out_path.exists() and out_path.stat().st_size > 0:
                    progress.advance(dl_task)
                    continue

                url = f"{base_url}/{quality_key}/{hash_code}/{filename}"
                r = self._request_with_retry("GET", url)
                with open(out_path, "wb") as f:
                    f.write(r.content)

                progress.advance(dl_task)

        console.print(f"[bold green]✓ Successfully downloaded all {len(filenames)} pages![/]")
        return dest_dir