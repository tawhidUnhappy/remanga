"""Per-project, per-chapter layout.

    projects/<manga>/
      project.json, manifest.json
      chapters/chapter_N/pages/         downloaded pages      (source)
      chapters/chapter_N/narration.json the LLM's narration   (source)
      pdf/chapter_N/pages_1.pdf, ...    upload for the LLM    (generated)
      audio/chapter_N/                  narration clips + audio_timing.json
      audio_modified/chapter_N/         the mixed master track
      video/chapter_N/<manga>_chN_recap.mp4, _work/
      logs/chapter_N.log                what the menus' work printed

A chapter's folder holds only what can't be rebuilt (pages, narration);
everything generated lives one level up, per kind."""

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
    return get_project_dir(project_name) / "chapters" / f"chapter_{_clean_chapter(chapter_num)}"


def get_pages_dir(project_name: str, chapter_num: str) -> Path:
    return get_chapter_dir(project_name, chapter_num) / "pages"


def get_panels_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """The panels cut out of this chapter's pages - what the LLM is shown and
    what the video plays."""
    path = get_chapter_dir(project_name, chapter_num) / "panels"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_crops_path(project_name: str, chapter_num: str) -> Path:
    """crops.json: the marks the Panel Marker saved for this chapter."""
    return get_chapter_dir(project_name, chapter_num) / "crops.json"


def get_narration_path(project_name: str, chapter_num: str) -> Path:
    return get_chapter_dir(project_name, chapter_num) / "narration.json"


GENERATED_KINDS = ("pdf", "audio", "audio_modified", "video")


def get_generated_dir(project_name: str, kind: str, chapter_num=None, create: bool = True) -> Path:
    """{manga}/{kind}/chapter_N/ (or {manga}/{kind}/ without a chapter)."""
    if kind not in GENERATED_KINDS:
        raise ValueError(f"Unknown generated-artifact kind: {kind!r} (expected one of {GENERATED_KINDS})")
    d = get_project_dir(project_name) / kind
    if chapter_num is not None:
        d = d / f"chapter_{_clean_chapter(chapter_num)}"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def get_pdf_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "pdf", chapter_num, create=create)


def get_audio_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """The synthesized narration clips and audio_timing.json - expensive to
    make, never deleted automatically."""
    return get_generated_dir(project_name, "audio", chapter_num, create=create)


def get_audio_timing_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_audio_dir(project_name, chapter_num, create=create) / "audio_timing.json"


def get_modified_audio_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """What the mix makes from audio/ - cheap to rebuild whenever a setting changes."""
    return get_generated_dir(project_name, "audio_modified", chapter_num, create=create)


def get_master_audio_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_modified_audio_dir(project_name, chapter_num, create=create) / "master_audio.wav"


def get_video_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
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
    """The encoded picture stream alone, so a sound-only change remuxes it
    instead of re-encoding every frame."""
    return get_video_work_dir(project_name, chapter_num, create=create) / "picture.mp4"


def get_log_path(project_name: str, chapter_num: str | None = None) -> Path:
    """What the menus' work printed, one file per chapter (or project.log for
    project-wide work) - kept out of the screen, one key away."""
    name = f"chapter_{_clean_chapter(chapter_num)}.log" if chapter_num is not None else "project.log"
    path = get_project_dir(project_name) / "logs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_final_video_path(project_name: str, chapter_num: str, create: bool = True) -> Path:
    video_dir = get_generated_dir(project_name, "video", chapter_num, create=create)
    return video_dir / f"{project_name}_ch{_clean_chapter(chapter_num)}_recap.mp4"
