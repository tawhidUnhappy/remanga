"""The MangaDex chapter-download picker: one screen showing every chapter
the manga has upstream, each already marked with whether this project has
it, so "download chapter 7" and "which chapters am I actually missing" are
the same look at the same list instead of two separate things to check.

Layered on downloader.mangadex.MangaDexDownloader: this module owns none of
the caching/verify/force-clean logic itself, only the interactive picker
around it (see MangaDexDownloader.list_chapters_with_status and
.download_chapters)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.downloader import MangaDexDownloader
from remanga.tui import Choice, confirm, is_cancel, multiselect, select

_REFETCH = "__refetch__"
_PICK = "__pick__"

_STATUS_BADGE = {"downloaded": "done", "partial": "partial", "missing": ""}


def _row_for(entry: Dict[str, Any]) -> Choice:
    pages = entry.get("pages")
    pages_note = f"{pages} page(s)" if pages else "page count unknown"
    title = f" - {entry['title']}" if entry.get("title") else ""
    return Choice(
        label=f"Chapter {entry['chapter']}{title}",
        hint=f"{entry['status']} · {pages_note}",
        badge=_STATUS_BADGE.get(entry["status"], ""),
        value=entry["chapter"],
        checked=entry["status"] != "downloaded",
    )


def run_download_chapters(project_name: str, config: RemangaConfig, manga_id_or_url: Optional[str] = None) -> None:
    """The whole interactive flow: fetch (cached up to 24h, refetchable on
    demand) -> pick chapters (pre-checked: everything not already fully
    downloaded) -> optionally force a clean reverify-and-redownload -> go.
    Picking the same chapter that's already downloaded is harmless either
    way - the normal path just re-verifies it and fills in anything
    missing, force wipes and refetches it from scratch."""
    downloader = MangaDexDownloader(config.downloader)

    force_refresh = False
    while True:
        try:
            entries = downloader.list_chapters_with_status(project_name, manga_id_or_url, force_refresh=force_refresh)
        except Exception as e:
            console.print(f"[bold red]Couldn't fetch the chapter list:[/] {e}")
            return
        if not entries:
            console.print("[yellow]MangaDex has no chapters listed for this manga in the configured language.[/]")
            return

        downloaded = sum(1 for e in entries if e["status"] == "downloaded")
        action_rows = [
            Choice(label="Pick chapters to download", hint=f"{downloaded}/{len(entries)} already downloaded",
                   value=_PICK),
            Choice(label="Refetch chapter list from MangaDex",
                   hint="bypass the 24h cache and check upstream again right now", value=_REFETCH),
        ]
        picked = select("Download chapters", action_rows, back_label="Back",
                        note="MangaDex's chapter feed is cached for 24h - use Refetch to check for new chapters now")
        if is_cancel(picked):
            return
        if picked == _REFETCH:
            force_refresh = True
            continue

        rows = [_row_for(entry) for entry in entries]
        chosen = multiselect(
            "Chapters to download", rows, allow_empty=False,
            note="pre-checked: everything not already fully downloaded · ctrl+a selects every chapter",
        )
        if is_cancel(chosen):
            continue  # back to the action menu, not out of the whole screen
        break

    force = confirm(
        "Reverify and download clean instead of just filling in what's missing?",
        default=False,
        note="wipes each selected chapter's pages first and re-downloads everything, even chapters "
             "already marked downloaded - use this if a chapter looks corrupted or was re-uploaded "
             "upstream; otherwise the normal (unchecked) path already verifies and only fetches "
             "what's actually missing",
    )

    try:
        downloader.download_chapters(project_name, chosen, manga_id_or_url, force=force)
    except Exception as e:
        console.print(f"[bold red]Download stopped:[/] {e}")
        return
    console.print(f"[bold green]✓ Done with {len(chosen)} chapter(s).[/]")
