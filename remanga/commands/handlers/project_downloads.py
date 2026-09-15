"""Project-wide download handlers: the whole manga, or a range of chapters."""

from __future__ import annotations

from typing import Any

from remanga.config import RemangaConfig
from remanga.console import console


def _mangadex_listing(params: dict[str, Any], config: RemangaConfig, *, refresh: bool):
    """A downloader, and every chapter MangaDex lists for this project's manga
    with its local status - empty, and said so, when there are none in the
    configured language."""
    from remanga.downloader import MangaDexDownloader

    downloader = MangaDexDownloader(config.downloader)
    entries = downloader.list_chapters_with_status(params["project"], params.get("url"), force_refresh=refresh)
    if not entries:
        console.print(
            f"[yellow]MangaDex lists no chapters in '{config.downloader.language}' for this "
            f"manga - nothing to download.[/]"
        )
    return downloader, entries


def download_all(params: dict[str, Any], config: RemangaConfig) -> None:
    """Every chapter MangaDex lists for this project's manga, downloaded.

    `download-chapters` already downloads several - but it is a *picker*:
    it exists to choose which ones, and choosing is exactly what "I want
    the whole manga" isn't. This asks nothing about which chapters, because
    the answer is all of them.

    What "all of them" means is the feed for this project's manga in the
    configured translation language (`downloader.language`, English by
    default), reduced to the newest upload of each chapter number - see
    MangaDexResolver.latest_versions for why a chapter can be in there more
    than once. Every chapter goes through download_chapter's own
    verify-and-fill-in-what's-missing path, so re-running this on a project
    that already has most of the manga costs a check per chapter and
    downloads only what's actually absent."""
    from remanga.tui import confirm, is_interactive

    project = params["project"]
    downloader, entries = _mangadex_listing(params, config, refresh=bool(params.get("refetch")))
    if not entries:
        return

    numbers = [entry["chapter"] for entry in entries]
    have = sum(1 for entry in entries if entry["status"] == "downloaded")
    console.print(
        f"[bold]{len(numbers)} chapter(s)[/] on MangaDex in "
        f"[bold]{config.downloader.language}[/] [dim](latest upload of each)[/] · "
        f"[green]{have} already downloaded[/] · [yellow]{len(numbers) - have} to fetch[/]"
    )
    # Only a real terminal is asked. A scripted `remanga download-all -p x`
    # already said what it wanted on the command line, and blocking it on a
    # confirmation nobody can answer would be the whole point of the flag,
    # undone.
    if is_interactive() and not confirm(
        f"Download all {len(numbers)} chapter(s) now?", default=True,
        note="already-downloaded chapters are verified, not re-fetched"
             + (" · --force re-fetches every one of them clean" if not params.get("force") else ""),
    ):
        return
    downloader.download_chapters(project, numbers, params.get("url"), force=bool(params.get("force")))


def download_range(params: dict[str, Any], config: RemangaConfig) -> None:
    """A run of chapters, downloaded - '1-5' is every chapter MangaDex lists
    numbered from 1 to 5, each decimal chapter a chapter of its own (1.1 and
    4.5 are in it, 5.1 comes after it), resolved by expand_chapter_selection.

    The listing is always fetched fresh rather than read from the 24h cache:
    a range is a question about which chapters exist, and a chapter
    published since yesterday is exactly the one somebody asks for. The
    range is asked for after that listing is shown, so the question comes
    with the answer's limits in front of it, and what it resolves to is
    shown before anything downloads.

    Chapters already downloaded go through download_chapter's re-verify:
    everything in pages/ that isn't one of the chapter's pages is removed,
    every page is checked against MangaDex's checksum, and only a page that
    fails is fetched again."""
    from remanga.full_recap.discovery import expand_chapter_selection
    from remanga.tui import ask_text, confirm, is_interactive

    project = params["project"]
    raw = (params.get("range") or "").strip()
    if not raw and not is_interactive():
        raise ValueError("--range is required when not running in an interactive terminal (e.g. --range 1-5).")

    downloader, entries = _mangadex_listing(params, config, refresh=True)
    if not entries:
        return
    available = [entry["chapter"] for entry in entries]
    downloaded = {entry["chapter"] for entry in entries if entry["status"] == "downloaded"}
    console.print(
        f"[bold]{len(available)} chapter(s)[/] on MangaDex in [bold]{config.downloader.language}[/]: "
        f"{available[0]} … {available[-1]} · [green]{len(downloaded)} already downloaded[/]"
    )

    if not raw:
        def check(text: str) -> str | None:
            try:
                return None if expand_chapter_selection(text, available, strict=True) else (
                    "No chapter on MangaDex falls in that range.")
            except ValueError as error:
                return str(error)

        raw = ask_text(
            "Chapters to download", allow_empty=False, validate=check,
            note="a range takes every chapter numbered from its start to its end - 1-5 includes 1.1 "
                 "and 4.5, not 5.1 · commas for more: 1-5,8,10-12",
        )
    chapters = expand_chapter_selection(raw, available, strict=True)
    if not chapters:
        console.print(f"[yellow]No chapter on MangaDex falls in '{raw}' - nothing to download.[/]")
        return

    have = [c for c in chapters if c in downloaded]
    console.print(
        f"[bold]{len(chapters)} chapter(s):[/] {', '.join(chapters)}\n"
        f"[dim]{len(chapters) - len(have)} to download · {len(have)} already here - re-verified page "
        f"by page, with anything in pages/ that isn't theirs removed[/]"
    )
    if is_interactive() and not confirm(
        f"Download these {len(chapters)} chapter(s)?", default=True,
        note="--force on the command line re-fetches every page clean instead",
    ):
        return
    downloader.download_chapters(project, chapters, params.get("url"), force=bool(params.get("force")))
    console.print(f"[bold green]✓ Chapters {raw}: all {len(chapters)} on disk and verified.[/]")
