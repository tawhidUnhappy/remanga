"""The steps of downloading one chapter's pages, each on its own - see
MangaDexDownloader.download_chapter (mangadex.py) for the order they run in."""

from __future__ import annotations

import time
from pathlib import Path

from remanga.chapters import page_stem
from remanga.console import console, escape as _esc
from remanga.paths import load_project_metadata, read_manifest, save_project_metadata, update_manifest_chapter
from remanga.plugins.mangadex.pages import PageFile, remove_paths


def remember_manga(resolver, project: str, source: str, manga_id: str, chapter: str) -> None:
    """The manga's identity in project.json. Resolving an ID/URL directly
    never learns the manga's title along the way, but the PDF's text page
    names the manga for the LLM, so it is fetched here - only when missing or
    the manga changed, not on every re-run of a downloaded chapter."""
    meta = load_project_metadata(project)
    title, language = meta.get("manga_title", ""), meta.get("original_language", "")
    if not title or not language or meta.get("manga_id") != manga_id:
        info = resolver.get_manga_info(manga_id)
        title, language = info["title"] or title, info["original_language"] or language
    save_project_metadata(project, {
        "project_name": project, "manga_url": source, "manga_id": manga_id, "manga_title": title,
        # What the reading direction is derived from instead of asking.
        "original_language": language, "last_chapter": str(chapter),
    })


def planned_pages(dest_dir: Path, chapter: str, files: list[str]) -> list[PageFile]:
    """Which file each MangaDex page is saved as, in reading order. A chapter
    MangaDex only links to (an official release on the publisher's site) has
    no files at all - said so, rather than 'verifying' zero pages."""
    if not files:
        raise ValueError(f"MangaDex has no pages for chapter {chapter} - it is only a link to the "
                         f"publisher's own site, so there is nothing to download.")
    return [PageFile(dest_dir / f"{page_stem(chapter, idx)}{Path(name).suffix or '.png'}", name)
            for idx, name in enumerate(files, start=1)]


def sweep_strays(dest_dir: Path, pages: list[PageFile], chapter: str) -> None:
    """pages/ holds exactly this chapter's pages: a stray file from an
    interrupted run, a manual copy, a folder, an old naming scheme - anything
    else is removed, and named, so it is visible."""
    expected = {page.path.name for page in pages}
    strays = sorted(p for p in dest_dir.iterdir() if p.name not in expected)
    if strays:
        names = ", ".join(p.name + ("/" if p.is_dir() else "") for p in strays)
        remove_paths(strays)
        console.print(f"[yellow]Removed {len(strays)} item(s) from pages/ that aren't chapter {_esc(chapter)}'s "
                      f"pages:[/] [dim]{_esc(names)}[/]")


def pages_to_fetch(project: str, chapter: str, pages: list[PageFile], chapter_id: str, quality: str) -> list[PageFile]:
    """Every page not on disk, or on disk and failing its checksum (removed).

    A page MangaDex gave no checksum for (never seen in practice) is trusted
    when the last attempt's record says nothing about a different chapter_id,
    quality or page count - re-fetching on a hunch is worse than trusting it."""
    cached = read_manifest(project).get("chapters", {}).get(str(chapter), {}).get("pages")
    trust_unchecked = not cached or (cached.get("chapter_id") == chapter_id and cached.get("quality") == quality
                                     and cached.get("total_pages") == len(pages))
    failed = [page for page in pages if page.path.exists() and not page.valid_on_disk(trust_unchecked)]
    if failed:
        remove_paths(page.path for page in failed)
        console.print(f"[yellow]{len(failed)} page(s) didn't match MangaDex's checksum - fetching them again.[/]")
    return [page for page in pages if not page.path.exists()]


def record_pages(project: str, chapter: str, chapter_id: str, manga_id: str, total: int, quality: str,
                 verified: bool) -> None:
    """The chapter's record in manifest.json, replaced on every attempt:
    `verified` is False before the first page is fetched and True only once
    every page is on disk and checked, so a run killed mid-download leaves a
    record saying so - the chapter listing reads it."""
    update_manifest_chapter(project, chapter, "pages", {
        "chapter_id": chapter_id, "manga_id": manga_id, "total_pages": total, "quality": quality,
        "timestamp": time.time(), "verified": verified,
    })
