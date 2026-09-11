from __future__ import annotations

import hashlib
import re
import shutil
import time
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.cropper.naming import page_stem
from remanga.downloader.resolve import BASE_URL, MangaDexResolver
from remanga.full_recap.discovery import chapter_key, chapter_sort_key  # direct submodule import -

# full_recap's own __init__ also pulls in compiler.py (audio/video stack),
# which this module has no other reason to import
from remanga.paths import (
    get_chapter_dir,
    get_pages_zip_path,
    load_project_metadata,
    read_manifest,
    read_remote_chapter_cache,
    save_project_metadata,
    update_manifest_chapter,
    write_remote_chapter_cache,
)

# How long a fetched MangaDex chapter feed is trusted before a plain
# "download"/"open the list" re-checks it automatically - a manga getting a
# new chapter mid-session is the normal case this guards against, while
# still sparing the feed API call (list_chapters paginates the whole feed)
# on every single menu open. Explicit refetch (force_refresh=True) always
# bypasses this regardless of age.
CHAPTER_LIST_CACHE_TTL_SECONDS = 24 * 60 * 60

# MangaDex@Home names every page file after the SHA-256 of its own bytes
# ("3-<64 hex digits>.png") - checked against real chapters at both image
# qualities. That's what makes re-verifying a downloaded chapter a check of
# each page's content rather than of its size.
_PAGE_CHECKSUM = re.compile(r"-([0-9a-f]{64})\.\w+$")

# config's image_quality -> (the at-home response's key for its file list,
# the URL path segment the files are served under). The smaller images are
# spelled differently in the two places, and config.py documents
# "data-saver", so both spellings are accepted.
_QUALITY = {
    "data": ("data", "data"),
    "data-saver": ("dataSaver", "data-saver"),
    "dataSaver": ("dataSaver", "data-saver"),
}


@dataclass(frozen=True)
class _Page:
    """One page of a chapter: where it's saved, and MangaDex's filename for it."""

    path: Path
    source: str

    @property
    def checksum(self) -> str | None:
        match = _PAGE_CHECKSUM.search(self.source)
        return match.group(1) if match else None

    def matches(self, content: bytes, trust_unchecked: bool = True) -> bool:
        """Whether `content` is this page: non-empty, and equal to MangaDex's
        checksum when it gave one (else `trust_unchecked` decides)."""
        if not content:
            return False
        if self.checksum is None:
            return trust_unchecked
        return hashlib.sha256(content).hexdigest() == self.checksum

    def valid_on_disk(self, trust_unchecked: bool) -> bool:
        return self.path.is_file() and self.matches(self.path.read_bytes(), trust_unchecked)


def _remove(paths: Iterable[Path]) -> None:
    """Deletes files, links and folders alike."""
    for path in list(paths):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


class MangaDexDownloader:
    def __init__(self, config: DownloaderConfig | None = None):
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
            _remove(dest_dir.iterdir())
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
        response_key, url_path = _QUALITY.get(quality_key, (quality_key, quality_key))
        pages = [
            _Page(dest_dir / f"{page_stem(chapter_num, idx)}{Path(fn).suffix or '.png'}", fn)
            for idx, fn in enumerate(chapter_data[response_key], start=1)
        ]

        # pages/ holds exactly this chapter's pages and nothing else - a stray
        # file from an interrupted run, a manual copy, a folder, an old naming
        # scheme. Anything else is removed, and named, so it's visible.
        expected = {page.path.name for page in pages}
        strays = sorted(p for p in dest_dir.iterdir() if p.name not in expected)
        if strays:
            names = ", ".join(p.name + ("/" if p.is_dir() else "") for p in strays)
            _remove(strays)
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
            _remove(page.path for page in failed)
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
                self._create_pages_zip(project_name, chapter_num, dest_dir)
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
            self._create_pages_zip(project_name, chapter_num, dest_dir)

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

    def _local_chapter_status(self, project_name: str, chapter_num: str, expected_pages: int | None) -> str:
        """One of "downloaded" (every expected page present and this
        chapter's cached pages-record says verified), "partial" (some
        pages on disk but not verified-complete for the current listing),
        or "missing" (nothing downloaded here yet). Purely a local disk +
        manifest check - no network call - so this is cheap enough to run
        for every chapter in a whole-manga listing."""
        pages_dir = get_chapter_dir(project_name, chapter_num) / "pages"
        on_disk = sum(1 for p in pages_dir.iterdir() if p.is_file()) if pages_dir.exists() else 0
        if on_disk == 0:
            return "missing"
        cached_meta = read_manifest(project_name).get("chapters", {}).get(str(chapter_num), {}).get("pages")
        if cached_meta and cached_meta.get("verified") and (
            expected_pages is None or cached_meta.get("total_pages") == expected_pages
        ):
            return "downloaded"
        return "partial"

    def list_chapters_with_status(
        self, project_name: str, manga_id_or_url: str | None = None, force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Every chapter MangaDex has for this project's manga, in reading
        order, each annotated with this project's own local download status
        ("downloaded" / "partial" / "missing") - the one call a chapter-
        picking menu needs to show "here's everything upstream, here's what
        you already have" in one screen.

        The MangaDex feed fetch itself (list_chapters, paginated) is cached
        in this project's manifest.json for CHAPTER_LIST_CACHE_TTL_SECONDS
        (24h) - a manga getting a new chapter is the only thing that ever
        changes it, so re-fetching on every menu open would just be a slow,
        rate-limited API call for almost always the same answer.
        force_refresh=True (the interactive "refetch from MangaDex" action)
        always bypasses the cache regardless of age. The local status
        annotation is never cached - it's a cheap disk check, and it must
        always reflect whatever was downloaded since the last fetch, cached
        chapter list or not."""
        manga_id = self._resolve_manga_id(project_name, manga_id_or_url)

        cached = read_remote_chapter_cache(project_name)
        cache_is_fresh = (
            not force_refresh
            and cached.get("manga_id") == manga_id
            and (time.time() - cached.get("fetched_at", 0)) < CHAPTER_LIST_CACHE_TTL_SECONDS
        )
        if cache_is_fresh:
            remote_chapters = cached["chapters"]
        else:
            # Deduplicated to one entry per chapter number, newest upload
            # kept - the same choice find_chapter_id makes when it goes to
            # fetch one, so what the picker lists and what a download
            # actually pulls can't disagree.
            raw_chapters = self.resolver.latest_versions(self.resolver.list_chapters(manga_id))
            remote_chapters = [
                {
                    "chapter": str(ch.get("attributes", {}).get("chapter") or ""),
                    "chapter_id": ch["id"],
                    "pages": ch.get("attributes", {}).get("pages"),
                    "title": ch.get("attributes", {}).get("title") or "",
                }
                for ch in raw_chapters
                if ch.get("attributes", {}).get("chapter")  # skip the odd chapterless "oneshot" entry
            ]
            remote_chapters.sort(key=lambda c: chapter_sort_key(c["chapter"]))
            write_remote_chapter_cache(project_name, manga_id, remote_chapters, time.time())

        for entry in remote_chapters:
            entry["status"] = self._local_chapter_status(project_name, entry["chapter"], entry.get("pages"))
        return remote_chapters

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
