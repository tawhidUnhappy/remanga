from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn

from remanga.config import DownloaderConfig, get_chapter_dir

console = Console()


class MangaDexDownloader:
    BASE_URL = "https://api.mangadex.org"

    def __init__(self, config: Optional[DownloaderConfig] = None):
        self.config = config or DownloaderConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "remanga-recap-pipeline/1.0"
        })

    def parse_manga_id(self, identifier: str) -> str:
        """Extract MangaDex UUID from a full URL or validate UUID format."""
        match = re.search(r"title/([a-f0-9\-]{36})", identifier)
        if match:
            return match.group(1)
        uuid_match = re.search(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", identifier.strip())
        if uuid_match:
            return identifier.strip()
        
        # Search by query if it is not a direct UUID
        return self.search_manga_by_title(identifier)

    def search_manga_by_title(self, title: str) -> str:
        """Search MangaDex for a manga title and return the first matching ID."""
        console.print(f"[cyan]Searching MangaDex for manga:[/] [bold]{title}[/]")
        res = self.session.get(
            f"{self.BASE_URL}/manga",
            params={"title": title, "limit": 5, "order[relevance]": "desc"}
        )
        res.raise_for_status()
        data = res.json().get("data", [])
        if not data:
            raise ValueError(f"No manga found on MangaDex matching query: '{title}'")
        
        manga_id = data[0]["id"]
        found_title = data[0]["attributes"]["title"].get("en") or list(data[0]["attributes"]["title"].values())[0]
        console.print(f"[green]Found:[/] {found_title} [dim]({manga_id})[/]")
        return manga_id

    def list_chapters(self, manga_id: str) -> List[Dict]:
        """Fetch all chapters for a manga filtered by language."""
        chapters = []
        limit = 100
        offset = 0
        
        with Progress(TextColumn("[progress.description]{task.description}"), BarColumn()) as progress:
            task = progress.add_task("[cyan]Fetching chapter feed...", total=None)
            while True:
                res = self.session.get(
                    f"{self.BASE_URL}/manga/{manga_id}/feed",
                    params={
                        "translatedLanguage[]": [self.config.language],
                        "order[chapter]": "asc",
                        "limit": limit,
                        "offset": offset
                    }
                )
                res.raise_for_status()
                data = res.json().get("data", [])
                if not data:
                    break
                chapters.extend(data)
                offset += limit
                if offset >= res.json().get("total", 0):
                    break
            progress.update(task, completed=100, total=100)

        return chapters

    def find_chapter_id(self, manga_id: str, chapter_num: str) -> str:
        """Locate specific chapter ID by chapter number."""
        chapters = self.list_chapters(manga_id)
        target = str(chapter_num).strip().lstrip("0")
        
        for ch in chapters:
            curr_num = str(ch["attributes"].get("chapter", "")).strip().lstrip("0")
            if curr_num == target or ch["attributes"].get("chapter") == chapter_num:
                return ch["id"]
                
        raise ValueError(f"Chapter '{chapter_num}' not found for manga ID: {manga_id}")

    def download_chapter(self, manga_id_or_url: str, chapter_num: str, project_name: str) -> Path:
        """Download high-resolution chapter images into project directory."""
        manga_id = self.parse_manga_id(manga_id_or_url)
        chapter_id = self.find_chapter_id(manga_id, chapter_num)
        
        dest_dir = get_chapter_dir(project_name, chapter_num) / "pages"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        console.print(f"[cyan]Retrieving MangaDex node for chapter {chapter_num}...[/]")
        at_home_res = self.session.get(f"{self.BASE_URL}/at-home/server/{chapter_id}")
        at_home_res.raise_for_status()
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
                downloaded = False

                for attempt in range(self.config.max_retries):
                    try:
                        r = self.session.get(url, timeout=30)
                        if r.status_code == 200:
                            with open(out_path, "wb") as f:
                                f.write(r.content)
                            downloaded = True
                            break
                    except Exception as e:
                        time.sleep(self.config.retry_delay_seconds * (attempt + 1))

                if not downloaded:
                    raise IOError(f"Failed to download page image: {url}")
                
                progress.advance(dl_task)

        console.print(f"[bold green]✓ Successfully downloaded all {len(filenames)} pages![/]")
        return dest_dir