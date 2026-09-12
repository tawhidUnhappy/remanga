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
#   2. `remanga/reset/` can wipe every generated artifact for a chapter (or a whole
#      project) by clearing these directories, without ever touching, or
#      needing to know the shape of, the source folder next to them.
GENERATED_KINDS = (
    "pages_zip", "sheets", "sheets_zip", "sheets_folders", "panels_zip",
    "panels_pdf", "audio", "audio_modified", "video",
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


def get_modified_audio_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """This chapter's DERIVED audio - everything that can be rebuilt from
    audio/ without going back to the TTS engine.

    The split is the point. `audio/` holds the raw synthesized narration and
    its timing: expensive to produce (minutes of GPU time per chapter) and
    the source of truth for everything downstream. `audio_modified/` holds
    what processing turns that into - the voice-chain-treated clips and the
    finished master. Those are cheap to reproduce and change whenever a
    setting changes, so they are a CACHE, not an artifact: losing them costs
    seconds, and the pipeline is free to throw them away and rebuild
    whenever their inputs no longer match (see audio/recipe.py).

    Before this split the two lived together, which meant "regenerate the
    audio" could only mean "re-synthesize everything" - changing a single
    dB of narration gain cost a full TTS run over every panel in the
    project."""
    return get_generated_dir(project_name, "audio_modified", chapter_num, create=create)


def get_modified_clip_path(project_name: str, chapter_num: str, audio_file: str,
                           create: bool = True) -> Path:
    """One panel's processed clip, alongside the raw one it was made from."""
    return get_modified_audio_dir(project_name, chapter_num, create=create) / audio_file


def get_master_audio_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """This chapter's own fully-mixed (narration + BGM + loudnorm) track.

    Derived, so it lives under audio_modified/ - a BGM or volume change
    rebuilds just this file (audio/mix.py, cheap) instead of anything
    upstream of it (TTS, frame compositing)."""
    return get_modified_audio_dir(project_name, chapter_num, create=create) / "master_audio.wav"


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


def get_video_picture_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """This chapter's encoded picture stream - video only, no sound. Kept
    apart from the final MP4 so a sound-only change remuxes it instead of
    re-encoding it, and so full-recap can stream-copy every chapter's
    picture into the join (see video/render.py)."""
    return get_video_work_dir(project_name, chapter_num, create=create) / "picture.mp4"


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
    compositing. See remanga/full_recap/, which builds these before joining them."""
    clean_chap = _clean_chapter(chapter_num)
    video_dir = get_generated_dir(project_name, "video", chapter_num, create=create)
    return video_dir / f"{project_name}_ch{clean_chap}_recap.mp4"


def find_full_recap_video(project_name: str) -> Path | None:
    """The most recently written whole-manga joined video for this project,
    if one exists - for callers that only need to know "is there one to
    rejoin/verify" without already knowing its exact chapter range (remix's
    rejoin check, verify's report). Globs rather than a fixed name since
    get_full_recap_video_path names the file after its own start/end
    chapter now - a project can (rarely) have more than one on disk after
    its chapter range changed between compiles; the newest by mtime is the
    one every other whole-manga command means by "the" full recap."""
    candidates = sorted(
        get_project_video_dir(project_name, create=False).glob(f"{project_name}_ch*_full_recap.mp4"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    ) if get_project_video_dir(project_name, create=False).exists() else []
    return candidates[0] if candidates else None


def get_full_recap_video_path(project_name: str, start_chapter: str, end_chapter: str) -> Path:
    """The whole-manga joined video - see remanga/full_recap/. Named with
    its own start/end chapter (e.g. "..._ch1-ch12_recap.mp4", or just
    "..._ch1_recap.mp4" for a single-chapter compile) so two different
    partial recaps of the same project - or the same one after a chapter
    range changed - never collide under one fixed filename, and which
    chapters a given file actually covers is readable from its name alone
    without opening it."""
    start_clean, end_clean = _clean_chapter(start_chapter), _clean_chapter(end_chapter)
    span = f"ch{start_clean}" if start_clean == end_clean else f"ch{start_clean}-ch{end_clean}"
    return get_project_video_dir(project_name) / f"{project_name}_{span}_full_recap.mp4"
