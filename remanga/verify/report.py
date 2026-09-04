"""Printing verification results - and, for anything that failed, the exact
command that fixes it. A report that says "corrupt" without saying what to
re-run just moves the problem."""

from __future__ import annotations

from remanga.console import console, escape as _esc
from remanga.verify.models import ChapterVerification, MediaCheck


def print_media_line(label: str, media: MediaCheck) -> None:
    if not media.exists:
        console.print(f"{label}: [red]missing[/]")
    elif not media.ok:
        console.print(f"{label}: [bold red]CORRUPT/TRUNCATED[/] - {_esc(media.error)}")
    else:
        console.print(f"{label}: [green]OK[/] [dim]({media.duration_sec:.1f}s)[/]")


def print_chapter_result(r: ChapterVerification) -> None:
    if r.narration_entries == 0:
        console.print(f"Chapter {r.chapter_num}: [dim]not started (no narration.json) - skipped[/]")
        return

    line = f"Chapter {r.chapter_num}: "
    if r.ok:
        console.print(line + "[green]OK[/]")
        return

    console.print(line + "[bold red]ISSUES FOUND[/]")
    if r.panel_narration_mismatch:
        console.print(f"  [red]panels/narration.json mismatch:[/] {_esc(r.panel_narration_mismatch)}")
        console.print(f"  [dim]-> fix: re-run crop/write/review for chapter {r.chapter_num} so panels and narration line up again[/]")
    if r.audio_clips_missing:
        console.print(f"  [red]{len(r.audio_clips_missing)}/{r.narration_entries} voice clip(s) missing:[/] {', '.join(r.audio_clips_missing[:10])}{' ...' if len(r.audio_clips_missing) > 10 else ''}")
        console.print(f"  [dim]-> fix: remanga tts --project <p> --chapter {r.chapter_num}[/]")
    if r.master_audio and not r.master_audio.ok:
        console.print(f"  [red]master_audio.wav corrupt/truncated:[/] {_esc(r.master_audio.error)}")
        console.print(f"  [dim]-> fix: remanga mix --project <p> --chapter {r.chapter_num}[/]")
    if r.video and not r.video.ok:
        console.print(f"  [red]chapter video corrupt/truncated:[/] {_esc(r.video.error)}")
        console.print(f"  [dim]-> fix: remanga render --project <p> --chapter {r.chapter_num} --force[/]")
    if r.duration_mismatch:
        console.print(f"  [red]{_esc(r.duration_mismatch)}[/]")
