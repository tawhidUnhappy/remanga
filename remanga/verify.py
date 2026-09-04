"""Integrity verification: strictly checks that every audio/video artifact a
chapter (or a whole project) claims to have is actually complete and
decodable, not just present on disk with a plausible size. Exists because
most of the pipeline's resume checks are deliberately cheap (file exists,
size > 1000 bytes) - fine for deciding whether to skip re-doing expensive
work, but not a real integrity guarantee. The two spots that genuinely can
be left corrupt by a kill at the wrong instant are the ones this checks
hardest: audio/mix.py's master_audio.wav (ffmpeg loudnorm writes it
directly, no atomic temp+rename) and video/render.py's final MP4 (same -
ffmpeg -y writes the destination in place). Per-panel TTS clips are NOT
re-probed one by one here: audio/tts.py's atomic_export already guarantees
those are either complete or entirely absent (temp file + rename into
place), so a corrupt-but-present clip literally cannot happen - only a
missing one can, and that's a fast existence/count check, not a decode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import has_real_json_content, read_json, read_json_or
from remanga.paths import (
    get_audio_dir, get_audio_timing_path, get_chapter_dir, get_final_video_path,
    get_full_recap_video_path, get_master_audio_path,
)


@dataclass
class MediaCheck:
    path: Path
    exists: bool = False
    decodable: bool = False
    duration_sec: Optional[float] = None
    has_audio: bool = False
    has_video: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exists and self.decodable and (self.duration_sec or 0) > 0


@dataclass
class ChapterVerification:
    chapter_num: str
    narration_entries: int = 0
    audio_clips_found: int = 0
    audio_clips_missing: List[str] = field(default_factory=list)
    master_audio: Optional[MediaCheck] = None
    video: Optional[MediaCheck] = None
    duration_mismatch: str = ""
    panel_narration_mismatch: str = ""

    @property
    def ok(self) -> bool:
        return (
            not self.audio_clips_missing
            and (self.master_audio is None or self.master_audio.ok)
            and (self.video is None or self.video.ok)
            and not self.duration_mismatch
            and not self.panel_narration_mismatch
        )


def check_panel_narration_mismatch(project_name: str, chapter_num: str) -> Optional[str]:
    """Fast, cheap cross-check between panels/ and narration.json's entries -
    no ffprobe/media decode, just directory listing + one JSON read, so it's
    safe to run automatically and often (the wizard runs this the moment a
    project is selected, not just via the `verify` command). Catches the
    exact footgun the remanga-ops skill calls out: narration.json's
    panel_id MUST equal the stem of a file in panels/ (render.py globs
    panels/*.png|*.jpg and keys off .stem) - a mismatch here usually means a
    re-crop happened after narration was written (or vice versa), silently
    leaving some panels unnarrated or some narration entries pointing at
    panels that no longer exist. Returns a one-line description if
    something's off, None if narration.json doesn't exist yet or everything
    lines up."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    narration_path = chapter_dir / "narration.json"
    if not has_real_json_content(narration_path):
        return None

    panels_dir = chapter_dir / "panels"
    panel_stems = {p.stem for p in panels_dir.iterdir() if p.is_file()} if panels_dir.exists() else set()

    narration = read_json(narration_path).get("narration", [])
    narration_ids = [e.get("panel_id") for e in narration]

    if len(narration_ids) == len(panel_stems) and set(narration_ids) == panel_stems:
        return None

    missing_panels = [pid for pid in narration_ids if pid not in panel_stems]
    extra_panels = sorted(panel_stems - set(narration_ids))
    parts = [f"{len(narration_ids)} narration entries vs {len(panel_stems)} panel file(s)"]
    if missing_panels:
        parts.append(
            f"{len(missing_panels)} narrated panel_id(s) with no matching panel file: "
            f"{', '.join(missing_panels[:5])}{' ...' if len(missing_panels) > 5 else ''}"
        )
    if extra_panels:
        parts.append(
            f"{len(extra_panels)} panel file(s) with no narration entry: "
            f"{', '.join(extra_panels[:5])}{' ...' if len(extra_panels) > 5 else ''}"
        )
    return "; ".join(parts)


def project_panel_narration_mismatches(project_name: str) -> List[tuple]:
    """Every chapter of this project with a panel/narration mismatch right
    now, as (chapter_num, issue) pairs - see check_panel_narration_mismatch.
    Cheap enough to call on every project selection, not just an explicit
    `verify` run."""
    from remanga.full_recap import discover_chapters, chapter_sort_key

    results = []
    for chapter_num in sorted(discover_chapters(project_name), key=chapter_sort_key):
        issue = check_panel_narration_mismatch(project_name, chapter_num)
        if issue:
            results.append((chapter_num, issue))
    return results


def probe_media(path: Path) -> MediaCheck:
    """Runs ffprobe on `path` and reports whether it's actually a complete,
    decodable media file - not just a file that exists. A truncated/corrupt
    file from a kill mid-write fails this even though `.exists()` and a
    size check would both pass it."""
    check = MediaCheck(path=path)
    if not path.exists() or path.stat().st_size == 0:
        check.error = "missing or empty"
        return check
    check.exists = True

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_type",
        "-of", "json", str(path),
    ]
    result = run_ffmpeg(cmd, capture=True)
    if result.returncode != 0:
        check.error = (result.stderr or "ffprobe failed").strip().splitlines()[-1][:200]
        return check

    try:
        data = json.loads(result.stdout or "{}")
    except Exception as e:
        check.error = f"unreadable ffprobe output: {e}"
        return check

    streams = data.get("streams", [])
    types = {s.get("codec_type") for s in streams}
    check.has_audio = "audio" in types
    check.has_video = "video" in types

    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    check.duration_sec = duration

    if not streams:
        check.error = "no decodable streams (likely truncated)"
        return check
    if duration <= 0:
        check.error = "zero/unreadable duration (likely truncated)"
        return check

    check.decodable = True
    return check


def verify_chapter(project_name: str, chapter_num: str, check_video: bool = True) -> ChapterVerification:
    result = ChapterVerification(chapter_num=chapter_num)

    narration_path = get_chapter_dir(project_name, chapter_num) / "narration.json"
    if not has_real_json_content(narration_path):
        return result  # nothing to verify yet - not an error, just not started

    narration = read_json(narration_path).get("narration", [])
    result.narration_entries = len(narration)
    panel_ids = [e.get("panel_id") or f"panel_{i:03d}" for i, e in enumerate(narration, start=1)]

    result.panel_narration_mismatch = check_panel_narration_mismatch(project_name, chapter_num) or ""

    audio_dir = get_audio_dir(project_name, chapter_num, create=False)
    for pid in panel_ids:
        clip = audio_dir / f"{pid}.wav"
        if clip.exists() and clip.stat().st_size > 0:
            result.audio_clips_found += 1
        else:
            result.audio_clips_missing.append(pid)

    master_audio_path = get_master_audio_path(project_name, chapter_num, create=False)
    if master_audio_path.exists():
        result.master_audio = probe_media(master_audio_path)

    if check_video:
        video_path = get_final_video_path(project_name, chapter_num, create=False)
        if video_path.exists():
            result.video = probe_media(video_path)

    # Cross-check: the mixed/rendered duration should roughly match the
    # timeline TTS itself produced - catches a master_audio.wav or video
    # that decodes fine but was silently truncated (a valid, playable, but
    # SHORT file - a corrupt-write pattern probe_media's decodability check
    # alone wouldn't catch).
    timing_path = get_audio_timing_path(project_name, chapter_num, create=False)
    expected_sec = None
    if timing_path.exists():
        timing = read_json_or(timing_path, {})
        expected_sec = timing.get("total_timeline_sec")
    if expected_sec:
        for label, media in (("master_audio.wav", result.master_audio), ("video", result.video)):
            if media and media.ok and media.duration_sec is not None:
                if media.duration_sec < expected_sec - 2.0:  # a couple seconds' ffmpeg/container slack is normal
                    result.duration_mismatch = (
                        f"{label} is {expected_sec - media.duration_sec:.1f}s shorter than the "
                        f"{expected_sec:.1f}s the synthesized audio timeline expects - likely truncated mid-write"
                    )

    return result


def verify_project(project_name: str, chapters: Optional[List[str]] = None, check_video: bool = True) -> List[ChapterVerification]:
    from remanga.full_recap import discover_chapters, chapter_sort_key

    chapter_list = sorted(chapters or discover_chapters(project_name), key=chapter_sort_key)
    results = []
    console.print(f"[bold cyan]Verifying {len(chapter_list)} chapter(s) of '{project_name}'...[/]")
    for chapter_num in chapter_list:
        r = verify_chapter(project_name, chapter_num, check_video=check_video)
        results.append(r)
        _print_chapter_result(r)

    full_video_path = get_full_recap_video_path(project_name)
    if full_video_path.exists():
        console.print("\n[bold]Full-recap joined video:[/]")
        full_check = probe_media(full_video_path)
        _print_media_line("  full-recap video", full_check)

    ok_count = sum(1 for r in results if r.ok)
    console.print(f"\n[bold]{ok_count}/{len(results)} chapter(s) fully verified.[/]")
    return results


def _print_media_line(label: str, media: MediaCheck) -> None:
    if not media.exists:
        console.print(f"{label}: [red]missing[/]")
    elif not media.ok:
        console.print(f"{label}: [bold red]CORRUPT/TRUNCATED[/] - {_esc(media.error)}")
    else:
        console.print(f"{label}: [green]OK[/] [dim]({media.duration_sec:.1f}s)[/]")


def _print_chapter_result(r: ChapterVerification) -> None:
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
