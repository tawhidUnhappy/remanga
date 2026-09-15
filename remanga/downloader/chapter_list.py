"""What MangaDex lists for a manga, next to what this project already has:
the chapter feed, cached for a day, with each chapter's local download
status - the one listing every chapter picker reads."""

from __future__ import annotations

import time
from typing import Any

# Straight from the submodule: full_recap's own __init__ also pulls in
# compiler.py (the audio/video stack), which a chapter listing has no need of.
from remanga.full_recap.discovery import chapter_sort_key
from remanga.paths import get_chapter_dir, read_manifest, read_remote_chapter_cache, write_remote_chapter_cache

# How long a fetched MangaDex chapter feed is trusted before a plain
# "download"/"open the list" re-checks it automatically - a manga getting a
# new chapter mid-session is the normal case this guards against, while
# still sparing the feed API call (list_chapters paginates the whole feed)
# on every single menu open. Explicit refetch (force_refresh=True) always
# bypasses this regardless of age.
CHAPTER_LIST_CACHE_TTL_SECONDS = 24 * 60 * 60


class ChapterListMixin:
    """MangaDexDownloader's chapter listing. Uses the downloader's `resolver`
    and `_resolve_manga_id`."""

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
