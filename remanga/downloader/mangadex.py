"""MangaDexDownloader: a chapter's pages fetched from MangaDex@Home and checked
page by page against the checksums MangaDex names them after (see
download_chapter). A page file is described in pages.py, the chapter listing
with local status is chapter_list.py, and resolving IDs, feeds and retries is
resolve.py, and each step of a chapter's download chapter_pages.py."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from remanga import activity
from remanga.chapters import chapter_key
from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.downloader.chapter_list import ChapterListMixin
from remanga.downloader.chapter_pages import (
    pages_to_fetch,
    planned_pages,
    record_pages,
    remember_manga,
    sweep_strays,
)
from remanga.downloader.pages import IMAGE_QUALITY, PageFile, remove_paths
from remanga.downloader.resolve import BASE_URL, MangaDexResolver
from remanga.paths import (
    get_chapter_dir,
    load_project_metadata,
)


class MangaDexDownloader(ChapterListMixin):
    def __init__(self, config: DownloaderConfig | None = None):
        self.config = config or DownloaderConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "remanga-recap-pipeline/2.0"
        })
        self.resolver = MangaDexResolver(self.config, self.session)

    def download_chapter(
        self, manga_id_or_url: str | None, chapter_num: str, project_name: str, force: bool = False,
        chapter_ids: dict[str, str] | None = None,
    ) -> Path:
        """Downloads a chapter's pages - or, for a chapter already here,
        re-verifies them and fetches only what's wrong or missing.

        Running it again on a downloaded chapter (the normal, `force=False`
        path) is always safe, and it is a real check rather than a glance:
        - pages/ is swept of everything that isn't one of this chapter's
          pages - a stray file, a leftover folder, an old naming scheme, a
          page from a different image_quality - and what went is named;
        - every page left is checked byte for byte against the SHA-256
          MangaDex names each page file after, and a page that doesn't match
          (truncated by a kill, corrupted, replaced upstream) is fetched again;
        - a freshly fetched page is checked the same way before it's written.
        `force=True` wipes pages/ first and fetches every page from scratch.

        `chapter_ids` is a MangaDexResolver.chapter_ids() result, passed by
        download_chapters so a bulk download reads the feed once rather than
        once per chapter."""
        dest_dir = get_chapter_dir(project_name, chapter_num) / "pages"
        if force and dest_dir.exists():
            remove_paths(dest_dir.iterdir())
            console.print(
                f"[yellow]Force reverify: cleared existing pages for chapter {chapter_num} before "
                f"re-downloading.[/]"
            )

        source = self._manga_source(project_name, manga_id_or_url)
        manga_id = self.resolver.parse_manga_id(source)
        remember_manga(self.resolver, project_name, source, manga_id, chapter_num)

        dest_dir.mkdir(parents=True, exist_ok=True)
        chapter_id = self.resolver.find_chapter_id(manga_id, chapter_num, chapter_ids)
        console.print(f"[cyan]Retrieving MangaDex node for chapter {chapter_num}...[/]")
        server_info = self.resolver.request_with_retry("GET", f"{BASE_URL}/at-home/server/{chapter_id}").json()
        chapter_data = server_info["chapter"]
        quality = self.config.image_quality
        response_key, url_path = IMAGE_QUALITY.get(quality, (quality, quality))
        pages = planned_pages(dest_dir, chapter_num, chapter_data[response_key])

        sweep_strays(dest_dir, pages, chapter_num)
        todo = pages_to_fetch(project_name, chapter_num, pages, chapter_id, quality)

        def record(verified: bool) -> None:
            record_pages(project_name, chapter_num, chapter_id, manga_id, len(pages), quality, verified)

        if not todo:
            record(True)
            console.print(
                f"[bold green]✓ All {len(pages)} pages verified against MangaDex's checksums - "
                f"nothing to download.[/]"
            )
            return dest_dir

        record(False)
        console.print(
            f"[green]Downloading {len(todo)} of {len(pages)} page(s) politely to:[/] {_esc(str(dest_dir))}"
        )
        base = f"{server_info['baseUrl']}/{url_path}/{chapter_data['hash']}"
        self._fetch(todo, base, chapter_num, len(pages))
        record(True)
        console.print(
            f"[bold green]✓ Downloaded {len(todo)} page(s) - all {len(pages)} verified against "
            f"MangaDex's checksums.[/]"
        )
        return dest_dir

    def _fetch(self, todo: list[PageFile], base: str, chapter_num: str, total: int) -> None:
        """The missing pages, one at a time and politely. Each is checked before
        it is written: a page that arrives damaged gets one more try, and a
        second bad copy stops the chapter rather than being recorded as verified."""
        with activity.progress(f"Downloading chapter {chapter_num}", total=total,
                               completed=total - len(todo), unit="pages") as bar:
            for page in todo:
                for _attempt in range(2):
                    content = self.resolver.request_with_retry("GET", f"{base}/{page.source}").content
                    if page.matches(content):
                        break
                else:
                    raise ValueError(
                        f"Page {page.path.name} of chapter {chapter_num} didn't match MangaDex's "
                        f"checksum twice in a row - try again later."
                    )
                page.path.write_bytes(content)
                if self.config.request_delay_seconds > 0:
                    time.sleep(self.config.request_delay_seconds)
                bar.advance()

    @staticmethod
    def _manga_source(project_name: str, manga_id_or_url: str | None) -> str:
        """The manga to download from: the one given, else the one this
        project saved the first time it downloaded anything."""
        if manga_id_or_url:
            return manga_id_or_url
        meta = load_project_metadata(project_name)
        saved = meta.get("manga_url") or meta.get("manga_id")
        if not saved:
            raise ValueError(
                f"No MangaDex URL or ID provided and none found saved for project '{project_name}'."
            )
        return saved

    def _resolve_manga_id(self, project_name: str, manga_id_or_url: str | None) -> str:
        return self.resolver.parse_manga_id(self._manga_source(project_name, manga_id_or_url))

    def download_chapters(
        self, project_name: str, chapter_nums: list[str], manga_id_or_url: str | None = None,
        force: bool = False,
    ) -> list[Path]:
        """Downloads several chapters in one call - "download all", a
        range, or an explicit multi-select all reduce to this. Duplicate
        chapter numbers are collapsed (picking one chapter twice in a
        multiselect is harmless, not a double-download) but order is kept
        stable via a first-seen pass rather than an unordered set. Each
        chapter still goes through download_chapter's own idempotent
        verify-and-fill-in-what's-missing logic (or, with force=True, its
        wipe-and-redo-clean path) - a failure on one chapter is reported and
        re-raised immediately rather than silently skipped, since a partial
        bulk download that looks like it finished is worse than one that
        stops where it broke.

        The feed is read once, up front, for every chapter's id - not once
        per chapter, which for a long manga was a whole paginated feed fetch
        per chapter downloaded."""
        seen: set = set()
        ordered_nums = [n for n in chapter_nums if not (chapter_key(n) in seen or seen.add(chapter_key(n)))]
        ids = self.resolver.chapter_ids(self._resolve_manga_id(project_name, manga_id_or_url))

        results: list[Path] = []
        for i, chapter_num in enumerate(ordered_nums, start=1):
            console.print(f"[bold cyan]({i}/{len(ordered_nums)}) Chapter {chapter_num}[/]")
            results.append(self.download_chapter(
                manga_id_or_url, chapter_num, project_name, force=force, chapter_ids=ids,
            ))
        return results
