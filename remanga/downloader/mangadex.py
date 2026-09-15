"""MangaDexDownloader: a chapter's pages fetched from MangaDex@Home and checked
page by page against the checksums MangaDex names them after (see
download_chapter). A page file is described in pages.py, the chapter listing
with local status is chapter_list.py, and resolving IDs, feeds and retries is
resolve.py."""

from __future__ import annotations

import time
from pathlib import Path

import requests
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.cropper.naming import page_stem
from remanga.downloader.chapter_list import ChapterListMixin
from remanga.downloader.pages import IMAGE_QUALITY, PageFile, create_pages_zip, remove_paths
from remanga.downloader.resolve import BASE_URL, MangaDexResolver

# Straight from the submodule: full_recap's own __init__ also pulls in
# compiler.py (the audio/video stack), which this module has no other reason
# to import.
from remanga.full_recap.discovery import chapter_key
from remanga.paths import (
    get_chapter_dir,
    load_project_metadata,
    read_manifest,
    save_project_metadata,
    update_manifest_chapter,
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

        manga_id_or_url = self._manga_source(project_name, manga_id_or_url)
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
        original_language = existing_meta.get("original_language", "")
        if not manga_title or not original_language or existing_meta.get("manga_id") != manga_id:
            info = self.resolver.get_manga_info(manga_id)
            manga_title = info["title"] or manga_title
            original_language = info["original_language"] or original_language

        save_project_metadata(project_name, {
            "project_name": project_name,
            "manga_url": manga_id_or_url,
            "manga_id": manga_id,
            "manga_title": manga_title,
            # Where the wizard derives reading_direction from instead of
            # asking - see remanga/wizard/projects.py.
            "original_language": original_language,
            "last_chapter": str(chapter_num)
        })

        dest_dir.mkdir(parents=True, exist_ok=True)
        chapter_id = self.resolver.find_chapter_id(manga_id, chapter_num, chapter_ids)

        console.print(f"[cyan]Retrieving MangaDex node for chapter {chapter_num}...[/]")
        server_info = self.resolver.request_with_retry("GET", f"{BASE_URL}/at-home/server/{chapter_id}").json()
        base_url = server_info["baseUrl"]
        chapter_data = server_info["chapter"]
        quality_key = self.config.image_quality
        response_key, url_path = IMAGE_QUALITY.get(quality_key, (quality_key, quality_key))
        pages = [
            PageFile(dest_dir / f"{page_stem(chapter_num, idx)}{Path(fn).suffix or '.png'}", fn)
            for idx, fn in enumerate(chapter_data[response_key], start=1)
        ]

        # pages/ holds exactly this chapter's pages and nothing else - a stray
        # file from an interrupted run, a manual copy, a folder, an old naming
        # scheme. Anything else is removed, and named, so it's visible.
        expected = {page.path.name for page in pages}
        strays = sorted(p for p in dest_dir.iterdir() if p.name not in expected)
        if strays:
            names = ", ".join(p.name + ("/" if p.is_dir() else "") for p in strays)
            remove_paths(strays)
            console.print(
                f"[yellow]Removed {len(strays)} item(s) from pages/ that aren't chapter {_esc(chapter_num)}'s "
                f"pages:[/] [dim]{_esc(names)}[/]"
            )

        # This chapter's record from the previous attempt, stored in the
        # project's shared manifest.json. Only consulted for a page MangaDex
        # gave no checksum for (never seen in practice): such a page is
        # trusted when nothing says it's for a different chapter_id, quality
        # or page count - a missing or interrupted record is still the same
        # chapter, and re-fetching on a hunch is worse than trusting it.
        cached_meta = read_manifest(project_name).get("chapters", {}).get(str(chapter_num), {}).get("pages")
        trust_unchecked = not cached_meta or (
            cached_meta.get("chapter_id") == chapter_id
            and cached_meta.get("quality") == quality_key
            and cached_meta.get("total_pages") == len(pages)
        )
        failed = [page for page in pages if page.path.exists() and not page.valid_on_disk(trust_unchecked)]
        if failed:
            remove_paths(page.path for page in failed)
            console.print(
                f"[yellow]{len(failed)} page(s) didn't match MangaDex's checksum - fetching them again.[/]"
            )
        todo = [page for page in pages if not page.path.exists()]

        def record_pages(verified: bool) -> None:
            # Replaced on every attempt, from the at-home response this
            # attempt resolved. `verified` is written False before the first
            # page is fetched and True only once every page is on disk and
            # checked, so a run killed mid-download leaves a record saying so
            # - the status panel and the download picker read it. No per-page
            # list: pages/ itself already shows that.
            update_manifest_chapter(project_name, chapter_num, "pages", {
                "chapter_id": chapter_id,
                "manga_id": manga_id,
                "total_pages": len(pages),
                "quality": quality_key,
                "timestamp": time.time(),
                "verified": verified,
            })

        if not todo:
            record_pages(True)
            console.print(
                f"[bold green]✓ All {len(pages)} pages verified against MangaDex's checksums - "
                f"nothing to download.[/]"
            )
            if self.config.zip_pages_enabled:
                create_pages_zip(project_name, chapter_num, dest_dir)
            return dest_dir

        record_pages(False)
        console.print(
            f"[green]Downloading {len(todo)} of {len(pages)} page(s) politely to:[/] {_esc(str(dest_dir))}"
        )

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
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            refresh_per_second=4,
        ) as progress:
            dl_task = progress.add_task("[yellow]Downloading pages...", total=len(pages),
                                        completed=len(pages) - len(todo))
            for page in todo:
                url = f"{base_url}/{url_path}/{chapter_data['hash']}/{page.source}"
                # Checked before it's written: a page that arrives damaged
                # gets one more try, and a second bad copy stops the chapter
                # rather than being recorded as verified.
                for _attempt in range(2):
                    content = self.resolver.request_with_retry("GET", url).content
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
                progress.advance(dl_task)

        record_pages(True)

        console.print(
            f"[bold green]✓ Downloaded {len(todo)} page(s) - all {len(pages)} verified against "
            f"MangaDex's checksums.[/]"
        )

        if self.config.zip_pages_enabled:
            create_pages_zip(project_name, chapter_num, dest_dir)

        return dest_dir

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
