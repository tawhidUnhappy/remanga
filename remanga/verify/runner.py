"""Running the checks: one chapter, or a whole project."""

from __future__ import annotations

from typing import List, Optional

from remanga.console import console
from remanga.json_io import has_real_json_content, read_json, read_json_or
from remanga.paths import (
    get_audio_dir, get_audio_timing_path, get_chapter_dir, get_final_video_path,
    get_full_recap_video_path, get_master_audio_path,
)
from remanga.verify.models import ChapterVerification
from remanga.verify.panels import check_panel_narration_mismatch
from remanga.verify.probe import probe_media
from remanga.verify.report import print_chapter_result, print_media_line


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
        print_chapter_result(r)

    full_video_path = get_full_recap_video_path(project_name)
    if full_video_path.exists():
        console.print("\n[bold]Full-recap joined video:[/]")
        full_check = probe_media(full_video_path)
        print_media_line("  full-recap video", full_check)

    ok_count = sum(1 for r in results if r.ok)
    console.print(f"\n[bold]{ok_count}/{len(results)} chapter(s) fully verified.[/]")
    return results


