"""Working out how far a chapter has got, from what's on disk.

Pure inspection - existence checks, directory counts and JSON reads, no
ffprobe and no config - so it's cheap enough for the wizard to call once per
row while drawing a chapter list. `verify` is the expensive counterpart that
actually decodes media.

Extensions add facts of their own and summary stages placed among the core
ones (remanga.extensions.StatusHooks)."""

from __future__ import annotations

from typing import Any

from remanga.extensions import Placed, SummaryStage, extension_status_hooks, place
from remanga.json_io import has_real_json_content, read_json_or
from remanga.paths import (
    get_audio_dir,
    get_audio_timing_path,
    get_chapter_dir,
    get_final_video_path,
    get_master_audio_path,
    get_narration_review_path,
    get_pages_zip_path,
    get_panels_pdf_dir,
    get_panels_zip_dir,
    get_sheets_dir,
    get_sheets_zip_dir,
)


def _tts_done(st: dict[str, Any]) -> bool:
    return st["total_narration_entries"] > 0 and st["audio_clips_count"] >= st["total_narration_entries"]


# A chapter's one-line summary: the first stage, from the most finished down,
# that recognizes where the chapter is.
CORE_SUMMARY_STAGES: tuple[SummaryStage, ...] = (
    SummaryStage("video", lambda st: "Recap Ready" if st["video_exist"] else None),
    SummaryStage("master_audio", lambda st: "Audio Ready (Pending Render)" if st["master_audio_exist"] else None),
    SummaryStage("tts_done", lambda st: "TTS Ready (Pending Mix)" if _tts_done(st) else None),
    SummaryStage("tts_progress", lambda st: (
        f"TTS In-Progress ({st['audio_clips_count']}/{st['total_narration_entries']})"
        if st["total_narration_entries"] > 0 and st["audio_clips_count"] > 0 else None)),
    SummaryStage("review", lambda st: (
        f"Narration Review Pending ({st['review_flagged_count']} flagged)"
        if st["review_pending"] and st["review_flagged_count"] > 0 else None)),
    SummaryStage("narration", lambda st: "Narration Script Ready" if st["narration_exist"] else None),
    SummaryStage("cropped", lambda st: f"Cropped ({st['panels_count']} panels)" if st["panels_count"] > 0 else None),
    SummaryStage("crops_json", lambda st: "Crops JSON Ready" if st["crops_exist"] else None),
    SummaryStage("pages", lambda st: f"Pages Ready ({st['pages_count']} pages)" if st["pages_count"] > 0 else None),
)


def summary_stages() -> list[SummaryStage]:
    return place(
        CORE_SUMMARY_STAGES,
        [Placed(stage, stage.after) for hooks in extension_status_hooks() for stage in hooks.summaries],
        lambda stage: stage.name,
    )


def get_chapter_status(project_name: str, chapter_num: str) -> dict[str, Any]:
    chap_dir = get_chapter_dir(project_name, chapter_num)
    pages_dir = chap_dir / "pages"
    panels_dir = chap_dir / "panels"
    sheets_dir = get_sheets_dir(project_name, chapter_num, create=False)
    audio_dir = get_audio_dir(project_name, chapter_num, create=False)
    panels_pdf_dir = get_panels_pdf_dir(project_name, chapter_num, create=False)
    narration_file = chap_dir / "narration.json"
    review_path = get_narration_review_path(project_name, chapter_num)
    final_video_path = get_final_video_path(project_name, chapter_num, create=False)

    narration_exist = has_real_json_content(narration_file)
    review_pending = has_real_json_content(review_path)
    st: dict[str, Any] = {
        "project": project_name,
        "chapter": str(chapter_num),
        "chap_dir": chap_dir,
        "pages_count": len([p for p in pages_dir.iterdir() if p.is_file()]) if pages_dir.exists() else 0,
        "pages_zip_exist": get_pages_zip_path(project_name, chapter_num, create=False).exists(),
        "crops_exist": has_real_json_content(chap_dir / "crops.json"),
        "panels_count": len([p for p in panels_dir.iterdir() if p.is_file()]) if panels_dir.exists() else 0,
        "sheets_count": len([p for p in sheets_dir.iterdir() if p.is_file()]) if sheets_dir.exists() else 0,
        # Any part of a package format existing counts as "built" - there's
        # no single "the" archive to check for anymore (see PackageConfig).
        "panels_zip_built": any(get_panels_zip_dir(project_name, chapter_num, create=False).glob("panels_*.zip")),
        "panels_pdf_built": any(panels_pdf_dir.glob("panels_*.pdf")) or any(panels_pdf_dir.glob("panels_*.zip")),
        "sheets_zip_built": any(get_sheets_zip_dir(project_name, chapter_num, create=False).glob("sheets_*.zip")),
        "narration_exist": narration_exist,
        "total_narration_entries": len(read_json_or(narration_file, {}).get("narration", []))
        if narration_exist else 0,
        "review_pending": review_pending,
        "review_flagged_count": read_json_or(review_path, {}).get("flagged_count", 0) if review_pending else 0,
        "audio_clips_count": (
            len([p for p in audio_dir.glob("*.wav") if not p.stem.endswith("_raw")]) if audio_dir.exists() else 0
        ),
        "timing_exist": get_audio_timing_path(project_name, chapter_num, create=False).exists(),
        "master_audio_exist": get_master_audio_path(project_name, chapter_num, create=False).exists(),
        "video_exist": final_video_path.exists() and final_video_path.stat().st_size > 1000,
        "video_path": final_video_path,
    }
    for hooks in extension_status_hooks():
        st.update(hooks.facts(project_name, chapter_num))

    st["summary"] = next(
        (text for stage in summary_stages() if (text := stage.describe(st)) is not None),
        "Not Started",
    )
    return st
