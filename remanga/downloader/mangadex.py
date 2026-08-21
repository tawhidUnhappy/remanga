from __future__ import annotations

import re
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn

from remanga.config import DownloaderConfig
from remanga.json_io import read_json_or, write_json
from remanga.paths import get_chapter_dir, load_project_metadata, save_project_metadata

console = Console()


class MangaDexDownloader:
    BASE_URL = "https://api.mangadex.org"

    def __init__(self, config: Optional[DownloaderConfig] = None):
        self.config = config or DownloaderConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "remanga-recap-pipeline/2.0"
        })

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
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
        """Fetch all chapters for a manga filtered by language with pagination and polite pacing."""
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

    def _create_pages_zip(self, chapter_dir: Path, pages_dir: Path) -> Path:
        """Package downloaded pages into a single ZIP archive for easy LLM uploading."""
        zip_path = chapter_dir / "pages.zip"
        if zip_path.exists():
            zip_path.unlink()

        pages = sorted(list(pages_dir.glob("page_*.*")))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in pages:
                zf.write(p, arcname=p.name)
            meta_json = chapter_dir / "pages_metadata.json"
            if meta_json.exists():
                zf.write(meta_json, arcname="pages_metadata.json")

        console.print(f"[bold green]✓ Created Pages ZIP archive:[/] {zip_path}")
        return zip_path

    def download_chapter(self, manga_id_or_url: Optional[str], chapter_num: str, project_name: str) -> Path:
        """Download high-resolution chapter images with idempotency check, metadata tracking, and auto-zip."""
        if not manga_id_or_url:
            meta = load_project_metadata(project_name)
            manga_id_or_url = meta.get("manga_url") or meta.get("manga_id")
            if not manga_id_or_url:
                raise ValueError(
                    f"No MangaDex URL or ID provided and none found saved for project '{project_name}'."
                )

        manga_id = self.parse_manga_id(manga_id_or_url)

        save_project_metadata(project_name, {
            "project_name": project_name,
            "manga_url": manga_id_or_url,
            "manga_id": manga_id,
            "last_chapter": str(chapter_num)
        })

        chapter_dir = get_chapter_dir(project_name, chapter_num)
        dest_dir = chapter_dir / "pages"
        dest_dir.mkdir(parents=True, exist_ok=True)
        meta_json_path = chapter_dir / "pages_metadata.json"

        chapter_id = self.find_chapter_id(manga_id, chapter_num)

        console.print(f"[cyan]Retrieving MangaDex node for chapter {chapter_num}...[/]")
        at_home_res = self._request_with_retry("GET", f"{self.BASE_URL}/at-home/server/{chapter_id}")
        server_info = at_home_res.json()

        base_url = server_info["baseUrl"]
        chapter_data = server_info["chapter"]
        hash_code = chapter_data["hash"]
        quality_key = self.config.image_quality
        filenames = chapter_data[quality_key]

        # Check existing pages & verify against metadata
        all_present = True
        cached_meta = read_json_or(meta_json_path, None)
        if cached_meta and cached_meta.get("total_pages") == len(filenames) and cached_meta.get("chapter_id") == chapter_id:
            for idx, fn in enumerate(filenames, start=1):
                page_ext = Path(fn).suffix or ".png"
                p_file = dest_dir / f"page_{idx:03d}{page_ext}"
                if not p_file.exists() or p_file.stat().st_size == 0:
                    all_present = False
                    break
        else:
            all_present = False

        if all_present:
            console.print(f"[bold green]✓ All {len(filenames)} pages verified and already downloaded! Skipping download.[/]")
            if self.config.create_zip:
                self._create_pages_zip(chapter_dir, dest_dir)
            return dest_dir

        console.print(f"[green]Downloading {len(filenames)} pages politely to:[/] {dest_dir}")

        downloaded_meta: List[Dict[str, Any]] = []

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
                    downloaded_meta.append({
                        "page_index": idx,
                        "filename": out_path.name,
                        "source_file": filename,
                        "size_bytes": out_path.stat().st_size
                    })
                    progress.advance(dl_task)
                    continue

                url = f"{base_url}/{quality_key}/{hash_code}/{filename}"
                r = self._request_with_retry("GET", url)
                with open(out_path, "wb") as f:
                    f.write(r.content)

                downloaded_meta.append({
                    "page_index": idx,
                    "filename": out_path.name,
                    "source_file": filename,
                    "size_bytes": out_path.stat().st_size
                })

                if self.config.request_delay_seconds > 0:
                    time.sleep(self.config.request_delay_seconds)

                progress.advance(dl_task)

        # Save verification metadata
        write_json(meta_json_path, {
            "project": project_name,
            "chapter": str(chapter_num),
            "chapter_id": chapter_id,
            "manga_id": manga_id,
            "total_pages": len(filenames),
            "quality": quality_key,
            "timestamp": time.time(),
            "pages": downloaded_meta
        })

        console.print(f"[bold green]✓ Successfully downloaded and verified all {len(filenames)} pages![/]")

        if self.config.create_zip:
            self._create_pages_zip(chapter_dir, dest_dir)

        return dest_dir