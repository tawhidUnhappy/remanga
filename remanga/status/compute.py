"""Working out how far a chapter has got, from what's on disk.

Pure inspection - existence checks, directory counts and JSON reads, no
ffprobe and no config - so it's cheap enough for the wizard to call once per
row while drawing a chapter list. `verify` is the expensive counterpart that
actually decodes media."""

from __future__ import annotations

from typing import Any, Dict

from remanga.json_io import has_real_json_content, read_json_or
from remanga.paths import (
    get_audio_dir, get_audio_timing_path, get_chapter_dir, get_final_video_path,
    get_master_audio_path, get_narration_review_path, get_pages_zip_path, get_panels_pdf_dir,
    get_panels_zip_dir, get_sheets_dir, get_sheets_zip_dir, get_youtube_path,
)


def get_chapter_status(project_name: str, chapter_num: str) -> Dict[str, Any]:
    chap_dir = get_chapter_dir(project_name, chapter_num)
    pages_dir = chap_dir / "pages"
    panels_dir = chap_dir / "panels"
    sheets_dir = get_sheets_dir(project_name, chapter_num, create=False)
    audio_dir = get_audio_dir(project_name, chapter_num, create=False)

    pages_count = len([p for p in pages_dir.iterdir() if p.is_file()]) if pages_dir.exists() else 0
    pages_zip_exist = get_pages_zip_path(project_name, chapter_num, create=False).exists()
    crops_exist = has_real_json_content(chap_dir / "crops.json")

    panels_count = len([p for p in panels_dir.iterdir() if p.is_file()]) if panels_dir.exists() else 0
    sheets_count = len([p for p in sheets_dir.iterdir() if p.is_file()]) if sheets_dir.exists() else 0
    # Any part of a package format existing counts as "built" - there's no
    # single "the" archive to check for anymore (see PackageConfig).
    panels_zip_built = any(get_panels_zip_dir(project_name, chapter_num, create=False).glob("panels_*.zip"))
    panels_pdf_dir = get_panels_pdf_dir(project_name, chapter_num, create=False)
    panels_pdf_built = any(panels_pdf_dir.glob("panels_*.pdf")) or any(panels_pdf_dir.glob("panels_*.zip"))
    sheets_zip_built = any(get_sheets_zip_dir(project_name, chapter_num, create=False).glob("sheets_*.zip"))

    narration_file = chap_dir / "narration.json"
    narration_exist = has_real_json_content(narration_file)
    total_narration_entries = 0
    if narration_exist:
        n_data = read_json_or(narration_file, {})
        total_narration_entries = len(n_data.get("narration", []))

    review_path = get_narration_review_path(project_name, chapter_num)
    review_pending = has_real_json_content(review_path)
    review_flagged_count = 0
    if review_pending:
        review_flagged_count = read_json_or(review_path, {}).get("flagged_count", 0)

    audio_clips_count = len([p for p in audio_dir.glob("*.wav") if not p.stem.endswith("_raw")]) if audio_dir.exists() else 0
    timing_exist = get_audio_timing_path(project_name, chapter_num, create=False).exists()
    master_audio_exist = get_master_audio_path(project_name, chapter_num, create=False).exists()

    youtube_exist = has_real_json_content(get_youtube_path(project_name, chapter_num))

    final_video_path = get_final_video_path(project_name, chapter_num, create=False)
    video_exist = final_video_path.exists() and final_video_path.stat().st_size > 1000

    if video_exist:
        summary = "Recap Ready"
    elif master_audio_exist:
        summary = "Audio Ready (Pending Render)"
    elif total_narration_entries > 0 and audio_clips_count >= total_narration_entries:
        summary = "TTS Ready (Pending Mix)"
    elif total_narration_entries > 0 and audio_clips_count > 0:
        summary = f"TTS In-Progress ({audio_clips_count}/{total_narration_entries})"
    elif review_pending and review_flagged_count > 0:
        summary = f"Narration Review Pending ({review_flagged_count} flagged)"
    elif narration_exist:
        summary = "Narration Script Ready"
    elif panels_count > 0:
        summary = f"Cropped ({panels_count} panels)"
    elif crops_exist:
        summary = "Crops JSON Ready"
    elif pages_count > 0:
        summary = f"Pages Ready ({pages_count} pages)"
    else:
        summary = "Not Started"

    return {
        "project": project_name,
        "chapter": str(chapter_num),
        "chap_dir": chap_dir,
        "pages_count": pages_count,
        "pages_zip_exist": pages_zip_exist,
        "crops_exist": crops_exist,
        "panels_count": panels_count,
        "sheets_count": sheets_count,
        "panels_zip_built": panels_zip_built,
        "panels_pdf_built": panels_pdf_built,
        "sheets_zip_built": sheets_zip_built,
        "narration_exist": narration_exist,
        "total_narration_entries": total_narration_entries,
        "review_pending": review_pending,
        "review_flagged_count": review_flagged_count,
        "audio_clips_count": audio_clips_count,
        "timing_exist": timing_exist,
        "master_audio_exist": master_audio_exist,
        "youtube_exist": youtube_exist,
        "video_exist": video_exist,
        "video_path": final_video_path,
        "summary": summary,
    }


