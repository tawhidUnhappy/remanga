"""ComixClient: comix.to, read through your Firefox (see __init__.py).

comix.to sits behind Cloudflare's check and signs and encrypts its own API, so
nothing here talks to the site directly: the helper opens the manga's page and
each chapter in your browser, the site's own reader loads the pages, and the
images it received are what is saved - byte for byte, at the size the site
serves them (the originals its page data names, when the reader shows smaller
ones). A chapter already here and whole is checked on disk and left alone,
without opening anything.

Politely: one chapter at a time, read at a reader's pace, a pause between
chapters, and the chapter list fetched at most once every 15 minutes."""

from __future__ import annotations

import io
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from remanga import activity
from remanga.chapters import chapter_key, chapter_sort_key, page_stem
from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json_or, write_json
from remanga.paths import (
    get_chapter_dir,
    get_project_dir,
    load_project_metadata,
    read_manifest,
    read_remote_chapter_cache,
    save_project_metadata,
    update_manifest_chapter,
    write_remote_chapter_cache,
)
from remanga.plugins.browser.bridge import HelperError
from remanga.plugins.browser.hooks import COMIX_TITLE
from remanga.plugins.browser.session import Session, helper_session
from remanga.plugins.mangadex.chapter_list import ChapterListMixin
from remanga.plugins.mangadex.chapter_pages import sweep_strays
from remanga.plugins.mangadex.pages import PageFile, remove_paths

SOURCE = "comix"
# The chapter list is trusted for a day; even an explicit refresh reuses one
# younger than this, so opening the chapter screen twice opens no page twice.
LIST_TTL_SECONDS = 24 * 60 * 60
LIST_REFRESH_FLOOR_SECONDS = 15 * 60
# The type comix.to gives a manga -> its original language (for the reading direction).
LANGUAGE_BY_TYPE = {"manga": "ja", "manhwa": "ko", "manhua": "zh"}
EXTENSION_BY_FORMAT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "AVIF": ".avif", "GIF": ".gif"}
# What the site's page may say a chapter is: anything else is dropped, never
# turned into a folder name or a link.
CHAPTER_NUMBER = re.compile(r"^\d{1,5}(\.\d{1,3})?$")
CHAPTER_ID = re.compile(r"^\d{1,12}$")

# A manga's page as last read in this run, by (manga, whole list read).
_TITLES: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}
# Every upload of the project's manga read so far (projects/<name>/comix-uploads.json):
# handed back to the helper, which then only turns the list when it has grown.
UPLOADS_FILE = "comix-uploads.json"


def _title_url(source: str) -> tuple[str, str]:
    """(the manga's id on comix.to, its title page) from any link to it."""
    match = COMIX_TITLE.match((source or "").strip())
    if not match:
        raise ValueError(f"Not a comix.to manga or chapter link: {source!r}")
    site, hid, slug = match.group(1).lower(), match.group(2).lower(), match.group(3)
    return hid, f"{site}/title/{hid}" + (f"-{slug}" if slug else "")


def _well_formed(chapter: dict[str, Any], site: str) -> bool:
    """A chapter as the page described it, checked: a plain number, a numeric
    id, and a link (if any) on the manga's own site."""
    number, ident, url = str(chapter.get("number", "")), str(chapter.get("id", "")), str(chapter.get("url") or "")
    if not (CHAPTER_NUMBER.match(number) and CHAPTER_ID.match(ident)):
        return False
    return not url or (urlparse(url).scheme in ("http", "https") and urlparse(url).netloc == urlparse(site).netloc)


def _best_per_number(chapters: list[dict[str, Any]], language: str, site: str = "") -> list[dict[str, Any]]:
    """One upload per chapter number - several groups often post the same
    chapter: the official one, else the most voted, else the newest."""
    chapters = [c for c in chapters if _well_formed(c, site)] if site else chapters
    if any(c.get("language") for c in chapters):
        same = [c for c in chapters if str(c.get("language", "")).lower().startswith(language.lower())]
        chapters = same or chapters
    best: dict[str, dict[str, Any]] = {}
    for c in chapters:
        key = chapter_key(c["number"])
        rank = (bool(c.get("official")), c.get("votes") or 0, int(c["id"]) if str(c["id"]).isdigit() else 0)
        if key not in best or rank > best[key]["_rank"]:
            best[key] = {**c, "_rank": rank}
    listing = [{"chapter": str(c["number"]), "chapter_id": str(c["id"]), "pages": c.get("pages") or None,
                "title": (c.get("name") or "").strip(), "group": (c.get("group") or "").strip(),
                "url": c.get("url", "")} for c in best.values()]
    return sorted(listing, key=lambda c: chapter_sort_key(c["chapter"]))


# The largest page taken, in pixels - read from the file's header before any
# decoding. Real pages are ~2-30 million; a "page" far bigger is a
# decompression bomb (a small file that unpacks into gigabytes).
MAX_PAGE_PIXELS = 50_000_000


def _check_image(content: bytes) -> tuple[str, int, int]:
    """(format, width, height) of a page's bytes, which must be a whole image."""
    with Image.open(io.BytesIO(content)) as image:
        if image.width * image.height > MAX_PAGE_PIXELS:
            raise ValueError(f"{image.width}x{image.height} is far larger than any page - refused")
        image.verify()
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        return image.format or "", image.width, image.height


class ComixClient(ChapterListMixin):
    def __init__(self, config: DownloaderConfig | None = None):
        self.config = config or DownloaderConfig()
        self._urls: dict[str, str] = {}

    # ---- the manga

    def parse_manga_id(self, source: str) -> str:
        hid, url = _title_url(source)
        self._urls[hid] = url
        return hid

    def _read_title(self, hid: str, session: Session | None = None, project: str | None = None) -> dict[str, Any]:
        """The manga's page; with `project`, its whole chapter list too."""
        whole = project is not None
        cached = _TITLES.get((hid, whole))
        if cached and time.time() - cached[0] < LIST_REFRESH_FLOOR_SECONDS:
            return cached[1]
        url = self._urls.get(hid) or f"https://comix.to/title/{hid}"
        if session is None:
            with helper_session(self.config) as own:
                return self._read_title(hid, own, project)
        uploads_path = get_project_dir(project) / UPLOADS_FILE if whole else None
        saved = read_json_or(uploads_path, {}) if uploads_path else {}
        known = saved.get("items", []) if saved.get("manga_id") == hid else []
        data = session.run("title", {"url": url, "hid": hid, "whole": whole, "known": known,
                                     "list_pause": self.config.browser_list_pause_seconds},
                           timeout=1800).result["data"]
        if uploads_path and data.get("chapters"):
            write_json(uploads_path, {"manga_id": hid, "items": data["chapters"]})
        _TITLES[(hid, whole)] = (time.time(), data)
        return data

    def get_manga_info(self, manga_id: str) -> dict[str, Any]:
        data = self._read_title(manga_id)
        title = " ".join(str(data.get("title") or "").split()) or manga_id
        alt = [str(t) for t in data.get("alt_titles") or []]
        english = title if title.isascii() else next((t for t in alt if t.isascii()), "")
        language = str(data.get("original_language") or LANGUAGE_BY_TYPE.get(str(data.get("type", "")).lower(), ""))
        formats = {str(f).strip().lower() for f in data.get("formats") or []}
        return {"title": title, "english_title": english, "original_language": language.lower(),
                # comix.to's "Long Strip" format, as MangaDex's tag of that name;
                # otherwise each chapter's images decide (remanga.layouts).
                "layout": "long_strip" if "long strip" in formats else None}

    # ---- the chapter list

    def _manga_source(self, project: str, url: str | None) -> str:
        source = url or load_project_metadata(project).get("manga_url")
        if not source:
            raise ValueError(f"No comix.to link saved for project '{project}'.")
        return source

    def _resolve_manga_id(self, project: str, url: str | None) -> str:
        return self.parse_manga_id(self._manga_source(project, url))

    def _remote_chapters(self, project: str, hid: str, force_refresh: bool,
                         session: Session | None = None) -> list[dict[str, Any]]:
        cached = read_remote_chapter_cache(project)
        age = time.time() - cached.get("fetched_at", 0) if cached.get("manga_id") == hid else float("inf")
        if age < (LIST_REFRESH_FLOOR_SECONDS if force_refresh else LIST_TTL_SECONDS):
            return cached["chapters"]
        try:
            data = self._read_title(hid, session, project) if session else self._read_title_briefly(hid, project)
        except HelperError:
            if cached.get("manga_id") == hid:
                console.print("[yellow]Firefox isn't reachable - using the chapter list from "
                              f"{int(age // 3600)} h ago.[/]")
                return cached["chapters"]
            raise
        found, total = data.get("chapters") or [], int(data.get("list_total") or 0)
        chapters = _best_per_number(found, self.config.language, self._urls.get(hid, ""))
        # The list's own rows, against the total it states (data-only mentions don't count).
        found = [c for c in found if c.get("listed")] or found
        if not chapters:
            raise HelperError("comix.to's page showed no chapters - the site may have changed; see "
                              ".cache/browser/last-title.json")
        if total and len(found) < total:
            # Used for this run, never kept: the next one reads the list again.
            console.print(f"[yellow]comix.to's list holds {total} uploads but {len(found)} were read - some "
                          f"chapters may be missing (see .cache/browser/last-title.json).[/]")
            activity.status(f"chapter list incomplete: {len(found)} of {total} uploads read - open it again")
        else:
            write_remote_chapter_cache(project, hid, chapters, time.time())
        return chapters

    def _read_title_briefly(self, hid: str, project: str) -> dict[str, Any]:
        """The manga's page, waiting up to two minutes for the helper (time
        for Firefox to start) - a list that can't be fetched falls back to
        the last one."""
        with helper_session(self.config, wait=120) as session:
            return self._read_title(hid, session, project)

    def list_chapters_with_status(self, project_name: str, manga_id_or_url: str | None = None,
                                  force_refresh: bool = False, session: Session | None = None) -> list[dict[str, Any]]:
        hid = self._resolve_manga_id(project_name, manga_id_or_url)
        chapters = [dict(c) for c in self._remote_chapters(project_name, hid, force_refresh, session)]
        for entry in chapters:
            entry["status"] = self._local_chapter_status(project_name, entry["chapter"], None)
        return chapters

    # ---- downloading

    def _whole_on_disk(self, project: str, chapter: str) -> bool:
        """A chapter this source downloaded and checked, still all there and
        every page still a whole image."""
        record = read_manifest(project).get("chapters", {}).get(str(chapter), {}).get("pages") or {}
        pages = get_chapter_dir(project, chapter) / "pages"
        files = sorted(p for p in pages.iterdir() if p.is_file()) if pages.exists() else []
        if record.get("source") != SOURCE or not record.get("verified") or len(files) != record.get("total_pages"):
            return False
        try:
            for path in files:
                _check_image(path.read_bytes())
        except Exception:
            return False
        return True

    def download_chapters(self, project_name: str, chapter_nums: list[str], manga_id_or_url: str | None = None,
                          force: bool = False) -> list[Path]:
        hid = self._resolve_manga_id(project_name, manga_id_or_url)
        seen: set[str] = set()
        ordered = [n for n in chapter_nums if not (chapter_key(n) in seen or seen.add(chapter_key(n)))]
        here = {n for n in ordered if not force and self._whole_on_disk(project_name, n)}
        for n in ordered:
            if n in here:
                console.print(f"[green]✓ Chapter {_esc(n)} is here and whole - nothing to download.[/]")
        todo = [n for n in ordered if n not in here]
        if todo:
            with helper_session(self.config, wait=None) as session:
                listing = {chapter_key(c["chapter"]): c
                           for c in self._remote_chapters(project_name, hid, False, session)}
                unknown = [n for n in todo if chapter_key(n) not in listing]
                if unknown:
                    raise ValueError(f"comix.to lists no chapter {', '.join(unknown)} for this manga.")
                for i, chapter in enumerate(todo, start=1):
                    session.pace_chapter()
                    console.print(f"[bold cyan]({i}/{len(todo)}) Chapter {_esc(chapter)}[/]")
                    try:
                        self._download(session, project_name, hid, chapter, listing[chapter_key(chapter)], force)
                    finally:
                        session.chapter_done()
        save_project_metadata(project_name, {"source": SOURCE, "manga_id": hid,
                                             "manga_url": self._manga_source(project_name, manga_id_or_url),
                                             "last_chapter": str(ordered[-1]) if ordered else ""})
        return [get_chapter_dir(project_name, n) / "pages" for n in ordered]

    def _download(self, session: Session, project: str, hid: str, chapter: str, entry: dict[str, Any],
                  force: bool) -> None:
        number, ident = str(entry.get("chapter", "")), str(entry.get("chapter_id", ""))
        if not (CHAPTER_NUMBER.match(number) and CHAPTER_ID.match(ident)):
            raise HelperError(f"Chapter {chapter}: the site's listing for it doesn't look right - not downloading it.")
        url = entry.get("url") or f"{self._urls[hid]}/{entry['chapter_id']}-chapter-{entry['chapter']}"
        if urlparse(url).netloc != urlparse(self._urls[hid]).netloc:
            raise HelperError(f"Chapter {chapter}: its link leaves the manga's site - not downloading it.")

        def record(total: int, verified: bool, extra: dict[str, Any] | None = None) -> None:
            update_manifest_chapter(project, chapter, "pages", {
                "source": SOURCE, "chapter_id": entry["chapter_id"], "manga_id": hid, "url": url,
                "total_pages": total, "quality": "original", "timestamp": time.time(), "verified": verified,
                **(extra or {}),
            })

        record(0, False)
        job = session.run("chapter", {
            "url": url, "hid": hid,
            "scroll_delay": self.config.browser_scroll_seconds,
            "request_delay": max(1.0, self.config.request_delay_seconds),
        }, timeout=1800)
        data = job.result["data"]
        total = int(data.get("pages") or 0)
        missing = [i for i in range(1, total + 1) if i not in job.pages]
        if not total or missing:
            raise HelperError(f"Chapter {chapter}: the helper sent {len(job.pages)} of {total} pages.")

        dest = get_chapter_dir(project, chapter) / "pages"
        planned: list[tuple[PageFile, bytes]] = []
        widths = []
        for index in range(1, total + 1):
            _type, content, source_url = job.pages[index]
            try:
                kind, width, _height = _check_image(content)
            except Exception as error:
                raise HelperError(f"Chapter {chapter} page {index} isn't a whole image ({error}) - "
                                  f"from {source_url[:120]}") from error
            widths.append(width)
            name = f"{page_stem(chapter, index)}{EXTENSION_BY_FORMAT.get(kind, '.' + kind.lower())}"
            planned.append((PageFile(dest / name, source_url), content))

        dest.mkdir(parents=True, exist_ok=True)
        if force:
            remove_paths(dest.iterdir())
        sweep_strays(dest, [page for page, _ in planned], chapter)
        for page, content in planned:
            partial = page.path.with_name(page.path.name + ".partial")
            partial.write_bytes(content)
            partial.replace(page.path)
        counts = data.get("counts") or {}
        record(total, True, {"from": data.get("source", ""), "width_min": min(widths), "width_max": max(widths)})
        fetched = counts.get("fetched", 0)
        console.print(
            f"[bold green]✓ {total} page(s), {min(widths)}-{max(widths)} px wide[/] [dim]("
            + ("from the page's own list of originals; " if data.get("source") == "page data" else "")
            + f"{counts.get('reader', 0)} as the reader loaded them"
            + (f", {fetched} fetched once more" if fetched else "")
            + (f", {counts['page']} read off the page" if counts.get("page") else "")
            + ")[/]"
        )
