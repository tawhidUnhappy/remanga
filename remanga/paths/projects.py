"""Per-project, per-chapter directory layout: where a chapter's source
material (pages/panels/crops.json/narration.json) lives vs. where every
generated artifact (sheets, zips/PDFs, audio, video) lives. See
get_chapter_dir's and GENERATED_KINDS' docstrings below for the split and
why it's deliberate."""

from __future__ import annotations

from pathlib import Path


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
