"""Project/chapter directory layout and metadata persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from remanga.json_io import read_json_or, write_json


def get_projects_dir() -> Path:
    p = Path("projects")
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_project_dir(project_name: str) -> Path:
    clean_proj = str(project_name).strip().replace("/", "_").replace("\\", "_")
    return get_projects_dir() / clean_proj


def _clean_chapter(chapter_num) -> str:
    return str(chapter_num).strip().replace("/", "_").replace("\\", "_")


def get_chapter_dir(project_name: str, chapter_num: str) -> Path:
    """The chapter's SOURCE folder only: pages/ (downloaded scans), panels/
    (cropped panel images), crops.json (panel marks) and narration.json (the
    narration script) - the handful of things that are either fetched from
    outside the pipeline or hand-authored, and so can't be regenerated from
    anything else remanga has. Every derived/generated artifact (sheets,
    zips/PDFs, audio, video, and this chapter's entry in manifest.json)
    lives one level up instead, under get_generated_dir() - see that
    function's docstring for why."""
    return get_project_dir(project_name) / "chapters" / f"chapter_{_clean_chapter(chapter_num)}"


# Every kind of artifact remanga can generate for a chapter, one flat set of
# project-level directories - {manga}/{kind}/chapter_N/ - instead of buried
# inside that chapter's own source folder. Two things this buys:
#   1. The chapter folder stays exactly what a human expects to find there
#      (downloads, crops, narration) - not fifteen kinds of byproduct sitting
#      next to the source, regardless of what config.json's package toggles
#      or production stage happen to be active.
#   2. `reset.py` can wipe every generated artifact for a chapter (or a whole
#      project) by clearing these directories, without ever touching, or
#      needing to know the shape of, the source folder next to them.
GENERATED_KINDS = (
    "pages_zip", "sheets", "sheets_zip", "sheets_folders", "panels_zip",
    "panels_pdf", "audio", "video",
)


def get_generated_dir(project_name: str, kind: str, chapter_num=None, create: bool = True) -> Path:
    """{manga}/{kind}/ if chapter_num is None (used for the manga-wide join
    outputs under kind="video"), else {manga}/{kind}/chapter_N/. `kind` must
    be one of GENERATED_KINDS - this is the one place that list is consulted
    to catch a typo'd kind early instead of quietly creating a stray
    directory. Pass create=False for a path a caller only wants to check
    (`.exists()`, glob a pattern) without the act of asking for the path
    itself creating an otherwise-empty directory - e.g. an inactive package
    format's would-be output dir."""
    if kind not in GENERATED_KINDS:
        raise ValueError(f"Unknown generated-artifact kind: {kind!r} (expected one of {GENERATED_KINDS})")
    d = get_project_dir(project_name) / kind
    if chapter_num is not None:
        d = d / f"chapter_{_clean_chapter(chapter_num)}"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def get_pages_zip_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "pages_zip", chapter_num, create=create) / "pages.zip"


def get_sheets_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "sheets", chapter_num, create=create)


def get_sheets_zip_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "sheets_zip", chapter_num, create=create)


def get_sheets_folders_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "sheets_folders", chapter_num, create=create)


def get_panels_zip_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "panels_zip", chapter_num, create=create)


def get_panels_pdf_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "panels_pdf", chapter_num, create=create)


def get_audio_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "audio", chapter_num, create=create)


def get_audio_timing_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_audio_dir(project_name, chapter_num, create=create) / "audio_timing.json"


def get_master_audio_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """This chapter's own fully-mixed (narration + BGM + loudnorm) track -
    kept, like get_final_video_path, so a later BGM/volume-only change can
    rebuild just this file (audio/mix.py, cheap) instead of everything
    upstream of it (TTS, frame compositing)."""
    return get_audio_dir(project_name, chapter_num, create=create) / "master_audio.wav"


def get_video_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """This chapter's own video/{kind} directory. Only ever holds two
    things: the finished MP4 itself (get_final_video_path) and one _work/
    subfolder for everything that builds it (frames/, concat_list.txt) - see
    get_video_work_dir. Keeping build artifacts out of this directory's own
    top level is deliberate: a bare `ls` here should only ever show "the
    video" and nothing that could be mistaken for another one, or for a
    working file left over from building it."""
    return get_generated_dir(project_name, "video", chapter_num, create=create)


def get_video_work_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    d = get_video_dir(project_name, chapter_num, create=create) / "_work"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def get_video_frames_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_video_work_dir(project_name, chapter_num, create=create) / "frames"


def get_video_concat_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_video_work_dir(project_name, chapter_num, create=create) / "concat_list.txt"


def get_project_video_dir(project_name: str, create: bool = True) -> Path:
    """{manga}/video/ - one chapter_N/ subfolder per chapter (see
    get_video_dir) plus the manga-wide full-recap join's own output
    directly here. Same "only the finished file(s) at this level" rule as
    get_video_dir: the join's own working audio/concat files live in
    get_full_recap_work_dir, not loose here next to the finished MP4."""
    return get_generated_dir(project_name, "video", create=create)


def get_full_recap_work_dir(project_name: str, create: bool = True) -> Path:
    d = get_project_video_dir(project_name, create=create) / "_work"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def get_full_recap_master_audio_path(project_name: str) -> Path:
    return get_full_recap_work_dir(project_name) / f"{project_name}_full_master.wav"


def get_full_recap_concat_path(project_name: str) -> Path:
    return get_full_recap_work_dir(project_name) / f"{project_name}_full_concat_list.txt"


def get_final_video_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """A single chapter's own final rendered MP4 - kept around (not a
    throwaway intermediate) specifically so a later BGM/volume-only change
    can rebuild just the mix + this file without re-running TTS or frame
    compositing. See full_recap.py, which builds these before joining them."""
    clean_chap = _clean_chapter(chapter_num)
    return get_generated_dir(project_name, "video", chapter_num, create=create) / f"{project_name}_ch{clean_chap}_recap.mp4"


def get_full_recap_video_path(project_name: str) -> Path:
    """The whole-manga joined video - see full_recap.py."""
    return get_project_video_dir(project_name) / f"{project_name}_full_recap.mp4"


def get_project_metadata_path(project_name: str) -> Path:
    return get_project_dir(project_name) / "project.json"


def get_memory_path(project_name: str) -> Path:
    return get_project_dir(project_name) / "memory.json"


def get_narration_review_path(project_name: str, chapter_num: str) -> Path:
    """The current review round's output, in the chapter's source folder
    right next to narration.json - written by the Narration Reviewer web UI
    (remanga/webui/reviewer_*.py), read by the user to hand to the LLM for a
    fix pass. Blanked (not deleted) once its round has been submitted, same
    convention as narration.json's own placeholder (json_io.has_real_json_content)."""
    return get_chapter_dir(project_name, chapter_num) / "narration_review.json"


def get_narration_review_history_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """Every past round's narration_review.json gets archived here as
    round_<n>.json before the live file is blanked for the next round - so a
    chapter's whole review history survives even though only the latest
    round is ever the "live" narration_review.json."""
    d = get_chapter_dir(project_name, chapter_num) / "narration_reviews"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def get_global_lessons_path() -> Path:
    """One file, shared by every project - not per-chapter or per-manga, and
    deliberately kept OUTSIDE projects/ (a sibling directory, not a
    subdirectory of it): list_projects() below treats every directory under
    projects/ as a manga project, so a "_global" folder living inside it
    used to show up as a bogus project in the wizard's project picker.
    Accumulates generalized narration mistakes/fixes an LLM has made across
    review rounds (see prompts/narration_review.md), phrased so they're
    useful on any manga, not just the one that surfaced them. Uploaded
    alongside narration.md/narration_review.md on every writing or review
    round so the same class of mistake doesn't recur project to project."""
    p = Path("global") / "narration_lessons.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def ensure_global_lessons_file() -> Path:
    """Creates a blank placeholder narration_lessons.json the first time
    it's needed, without ever clobbering lessons an LLM has already written
    there - same pattern as ensure_memory_file()."""
    p = get_global_lessons_path()
    if not p.exists():
        p.write_text("", encoding="utf-8")
    return p


def ensure_memory_file(project_name: str) -> Path:
    """Creates a blank placeholder memory.json at the project root the first time a project
    is touched, without ever clobbering continuity data an LLM has already written there."""
    memory_path = get_memory_path(project_name)
    if not memory_path.exists():
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text("", encoding="utf-8")
    return memory_path


def load_project_metadata(project_name: str) -> Dict[str, Any]:
    return read_json_or(get_project_metadata_path(project_name), {})


def chapter_identity_fields(project_name: str, chapter_num: str) -> Dict[str, Any]:
    """The project/manga/chapter identity fields every chapter_info.json starts
    from - shared by the primary vision archive (cropper/crop_report.py's
    write_chapter_info) and the size-capped LLM zip bundle (cropper/llm_zip.py),
    which adds its own part_index/total_parts per part on top of this same
    dict. See prompts/narration.md's "Chapter Identity" section for how the
    LLM is expected to read whichever of those it's handed."""
    meta = load_project_metadata(project_name)
    return {
        "project_name": project_name,
        "manga_name": meta.get("manga_title", ""),
        "manga_url": meta.get("manga_url", ""),
        "chapter": str(chapter_num),
    }


def save_project_metadata(project_name: str, data: Dict[str, Any]) -> None:
    meta_path = get_project_metadata_path(project_name)
    existing = load_project_metadata(project_name)
    existing.update(data)
    write_json(meta_path, existing)
    ensure_memory_file(project_name)


def get_manifest_path(project_name: str) -> Path:
    """{manga}/manifest.json - ONE file for the whole project carrying the
    informational bookkeeping that used to be three separate, never-read-back
    files repeated in every chapter folder (pages_metadata.json,
    panels_manifest.json, chapter_info.json). Keyed by chapter number, one
    section per production stage that wants to record something about a
    chapter (currently "pages" and "panels") - deliberately kept to small
    summary fields only (counts, ids, a timestamp), never a per-item dump.
    A per-panel/per-page listing (path, crop box, width/height, ...) is
    exactly the bloat those three files were replaced to get rid of - that
    detail already lives in full wherever it's actually needed (panels/
    itself, each package format's own per-part manifest), so repeating it
    here a second time just to sit unread would recreate the same problem
    under a new filename. If a future caller genuinely needs per-item data
    back, resist the urge to reach for this file - it means the caller
    should read the real source (panels/, pages/) instead."""
    return get_project_dir(project_name) / "manifest.json"


def read_manifest(project_name: str) -> Dict[str, Any]:
    return read_json_or(get_manifest_path(project_name), {"chapters": {}})


def update_manifest_chapter(project_name: str, chapter_num: str, section: str, data: Any) -> None:
    """Read-modify-write manifest.json['chapters'][chapter_num][section] = data.
    Chapters/sections are independent - downloader writes "pages" (called
    once per chapter, well before cropping touches this file), cropper
    writes "panels" (called once per chapter, after downloader already has)
    - so there's no cross-stage write race within a single chapter's
    production run, and each stage only ever rewrites its own section,
    never another chapter's or another stage's."""
    manifest = read_manifest(project_name)
    manifest.setdefault("chapters", {}).setdefault(str(chapter_num), {})[section] = data
    write_json(get_manifest_path(project_name), manifest)


def list_projects() -> List[Dict[str, Any]]:
    root = get_projects_dir()
    results = []
    if not root.exists():
        return results

    # Case-insensitive so e.g. "reincarnated..." (lowercase r) doesn't sort
    # after every capitalized project name - plain sorted() on Path objects
    # is ASCII/case-sensitive, which reads as a scrambled, seemingly
    # unstable order to anyone not thinking in ASCII code points.
    for p in sorted(root.iterdir(), key=lambda entry: entry.name.casefold()):
        if p.is_dir():
            meta = load_project_metadata(p.name)
            chapters_dir = p / "chapters"
            chapters = []
            if chapters_dir.exists():
                for c in sorted(chapters_dir.iterdir()):
                    if c.is_dir() and c.name.startswith("chapter_"):
                        ch_num = c.name.replace("chapter_", "")
                        chapters.append(ch_num)
            results.append({
                "name": p.name,
                "path": p,
                "manga_url": meta.get("manga_url", ""),
                "manga_id": meta.get("manga_id", ""),
                "last_chapter": meta.get("last_chapter", ""),
                "chapters": chapters,
            })
    return results
