from __future__ import annotations

import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn

from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.cropper.naming import page_stem
from remanga.downloader.resolve import BASE_URL, MangaDexResolver
from remanga.paths import get_chapter_dir, get_pages_zip_path, load_project_metadata, read_manifest, save_project_metadata, update_manifest_chapter


class MangaDexDownloader:
    def __init__(self, config: Optional[DownloaderConfig] = None):
        self.config = config or DownloaderConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "remanga-recap-pipeline/2.0"
        })
        self.resolver = MangaDexResolver(self.config, self.session)

    def _create_pages_zip(self, project_name: str, chapter_num: str, pages_dir: Path) -> Path:
        """Package downloaded pages into a single ZIP archive for easy LLM uploading."""
        zip_path = get_pages_zip_path(project_name, chapter_num)
        if zip_path.exists():
            zip_path.unlink()

        pages = sorted(p for p in pages_dir.iterdir() if p.is_file())
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in pages:
                zf.write(p, arcname=p.name)

        console.print(f"[bold green]✓ Created Pages ZIP archive:[/] {_esc(str(zip_path))}")
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

        manga_id = self.resolver.parse_manga_id(manga_id_or_url)

        # Resolving an ID/URL directly (as opposed to a title search - see
        # MangaDexResolver.parse_manga_id) never otherwise learns the manga's
        # actual title along the way, but cropper/crop_report.py's
        # chapter_info.json (bundled into the vision zip - see
        # prompts/narration.md) needs a human-readable name for the LLM, so
        # fetch and cache it here. Only re-fetched when missing or the manga
        # ID changed, to avoid an extra API call on every re-run of an
        # already-downloaded chapter.
        existing_meta = load_project_metadata(project_name)
        manga_title = existing_meta.get("manga_title", "")
        if not manga_title or existing_meta.get("manga_id") != manga_id:
            manga_title = self.resolver.get_manga_title(manga_id)

        save_project_metadata(project_name, {
            "project_name": project_name,
            "manga_url": manga_id_or_url,
            "manga_id": manga_id,
            "manga_title": manga_title,
            "last_chapter": str(chapter_num)
        })

        chapter_dir = get_chapter_dir(project_name, chapter_num)
        dest_dir = chapter_dir / "pages"
        dest_dir.mkdir(parents=True, exist_ok=True)

        chapter_id = self.resolver.find_chapter_id(manga_id, chapter_num)

        console.print(f"[cyan]Retrieving MangaDex node for chapter {chapter_num}...[/]")
        at_home_res = self.resolver.request_with_retry("GET", f"{BASE_URL}/at-home/server/{chapter_id}")
        server_info = at_home_res.json()

        base_url = server_info["baseUrl"]
        chapter_data = server_info["chapter"]
        hash_code = chapter_data["hash"]
        quality_key = self.config.image_quality
        filenames = chapter_data[quality_key]

        # Every page this chapter is expected to have, by its new
        # {chapter}_{page} filename - built up front (not just up to the
        # first missing one) so the stray-file cleanup below always has the
        # complete set to check against.
        expected_names = {
            f"{page_stem(chapter_num, idx)}{Path(fn).suffix or '.png'}"
            for idx, fn in enumerate(filenames, start=1)
        }

        # Drop anything in pages_dir that doesn't belong there - a stray file
        # left over from an interrupted run, a manual copy, an old naming
        # scheme, or a leftover page from a different `image_quality`
        # setting - so pages_dir always holds exactly this chapter's
        # downloaded pages, nothing else.
        for stray in dest_dir.iterdir():
            if stray.is_file() and stray.name not in expected_names:
                stray.unlink()

        # Check existing pages & verify against metadata - stored in this
        # project's shared manifest.json (see paths.update_manifest_chapter)
        # instead of a per-chapter pages_metadata.json file, since this is
        # the only thing that ever reads it back.
        all_present = True
        cached_meta = read_manifest(project_name).get("chapters", {}).get(str(chapter_num), {}).get("pages")
        if cached_meta and cached_meta.get("total_pages") == len(filenames) and cached_meta.get("chapter_id") == chapter_id:
            for idx, fn in enumerate(filenames, start=1):
                page_ext = Path(fn).suffix or ".png"
                p_file = dest_dir / f"{page_stem(chapter_num, idx)}{page_ext}"
                if not p_file.exists() or p_file.stat().st_size == 0:
                    all_present = False
                    break
        else:
            all_present = False

        if all_present:
            console.print(f"[bold green]✓ All {len(filenames)} pages verified and already downloaded! Skipping download.[/]")
            if self.config.zip_pages_enabled:
                self._create_pages_zip(project_name, chapter_num, dest_dir)
            return dest_dir

        console.print(f"[green]Downloading {len(filenames)} pages politely to:[/] {_esc(str(dest_dir))}")

        downloaded_meta: List[Dict[str, Any]] = []

        # refresh_per_second=4 (Rich's default is ~10): a long-lived Progress
        # bar redraws itself that many times a second regardless of whether
        # anything is actually reading the terminal's output - if the
        # terminal emulator stops draining its side while the screen is
        # locked for a while, the OS pty buffer fills at whatever rate this
        # writes, and once it's full the next write blocks until something
        # drains it, which reads as the whole pipeline "getting stuck" until
        # unlock. 4Hz is still smooth to watch and cuts that write volume by
        # more than half; it doesn't make the buffer un-fillable, just a lot
        # slower to fill for the same locked duration.
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TimeRemainingColumn(),
            refresh_per_second=4,
        ) as progress:
            dl_task = progress.add_task("[yellow]Downloading pages...", total=len(filenames))

            for idx, filename in enumerate(filenames, start=1):
                page_ext = Path(filename).suffix or ".png"
                out_path = dest_dir / f"{page_stem(chapter_num, idx)}{page_ext}"

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
                r = self.resolver.request_with_retry("GET", url)
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

        # Save verification metadata into this project's shared manifest.json
        update_manifest_chapter(project_name, chapter_num, "pages", {
            "chapter_id": chapter_id,
            "manga_id": manga_id,
            "total_pages": len(filenames),
            "quality": quality_key,
            "timestamp": time.time(),
            "pages": downloaded_meta,
        })

        console.print(f"[bold green]✓ Successfully downloaded and verified all {len(filenames)} pages![/]")

        if self.config.zip_pages_enabled:
            self._create_pages_zip(project_name, chapter_num, dest_dir)

        return dest_dir
