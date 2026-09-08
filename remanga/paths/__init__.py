"""remanga's single source of truth for every filesystem path it touches -
where the repo/binaries/isolated tool envs live (roots.py, tools.py), where
the two web UIs' static assets are (webui_static.py), per-project/per-chapter
directory layout (projects.py), project-level metadata files (metadata.py),
narration-review-round files (review.py), and cross-project shared assets
(global_assets.py).

Split into one file per concern instead of one growing file, the same
reasoning as remanga/config/'s split: each of these is independent of the
others and only ever changes for its own reason (a new generated-artifact
kind doesn't touch how config.json is located; a new tool venv doesn't touch
per-chapter directory layout). This __init__ re-exports the full flat
surface so every existing `from remanga.paths import X` elsewhere in the
codebase keeps working completely unchanged - this package boundary is
invisible to every caller.

To add a new path: pick the module it belongs with (or add one, for a
genuinely new concern), write one function/constant there, add it to
__all__ below. Never construct a path inline elsewhere in the codebase with
Path(__file__)/Path("literal")/REPO_ROOT-style code - that's the exact
duplication (config.json's path used to be defined separately in three
different files) this package exists to rule out. If a call site needs a
path this package doesn't have yet, add it here first."""

from __future__ import annotations

from .global_assets import (
    ensure_global_lessons_file,
    ensure_hf_token_file,
    get_global_lessons_path,
    get_hf_token_path,
)
from .metadata import (
    chapter_identity_fields,
    ensure_memory_file,
    get_manifest_path,
    get_memory_path,
    get_pipeline_path,
    get_project_metadata_path,
    list_projects,
    load_project_metadata,
    read_manifest,
    read_remote_chapter_cache,
    save_project_metadata,
    update_manifest_chapter,
    write_remote_chapter_cache,
)
from .projects import (
    GENERATED_KINDS,
    find_full_recap_video,
    get_audio_dir,
    get_audio_timing_path,
    get_chapter_dir,
    get_final_video_path,
    get_full_recap_concat_path,
    get_full_recap_master_audio_path,
    get_full_recap_video_path,
    get_full_recap_work_dir,
    get_generated_dir,
    get_master_audio_path,
    get_pages_zip_path,
    get_panels_pdf_dir,
    get_panels_zip_dir,
    get_project_dir,
    get_project_video_dir,
    get_projects_dir,
    get_sheets_dir,
    get_sheets_folders_dir,
    get_sheets_zip_dir,
    get_video_concat_path,
    get_video_dir,
    get_video_frames_dir,
    get_video_work_dir,
)
from .review import get_narration_review_history_dir, get_narration_review_path
from .roots import BIN_DIR, CONFIG_EXAMPLE_PATH, CONFIG_PATH, GLOBAL_DIR, REPO_ROOT, TOOLS_DIR, UV_BIN
from .tools import get_scripts_dir, get_tool_python
from .webui_static import MARKER_STATIC_DIR, REVIEWER_STATIC_DIR, WRITER_STATIC_DIR

__all__ = [
    "BIN_DIR",
    "CONFIG_EXAMPLE_PATH",
    "CONFIG_PATH",
    "GENERATED_KINDS",
    "GLOBAL_DIR",
    # webui static
    "MARKER_STATIC_DIR",
    # roots
    "REPO_ROOT",
    "REVIEWER_STATIC_DIR",
    "TOOLS_DIR",
    "UV_BIN",
    "WRITER_STATIC_DIR",
    "chapter_identity_fields",
    "ensure_global_lessons_file",
    "ensure_hf_token_file",
    "ensure_memory_file",
    "find_full_recap_video",
    "get_audio_dir",
    "get_audio_timing_path",
    "get_chapter_dir",
    "get_final_video_path",
    "get_full_recap_concat_path",
    "get_full_recap_master_audio_path",
    "get_full_recap_video_path",
    "get_full_recap_work_dir",
    "get_generated_dir",
    # global assets
    "get_global_lessons_path",
    "get_hf_token_path",
    "get_manifest_path",
    "get_master_audio_path",
    "get_memory_path",
    "get_narration_review_history_dir",
    # review
    "get_narration_review_path",
    "get_pages_zip_path",
    "get_panels_pdf_dir",
    "get_panels_zip_dir",
    "get_pipeline_path",
    "get_project_dir",
    # metadata
    "get_project_metadata_path",
    "get_project_video_dir",
    # projects/chapters
    "get_projects_dir",
    "get_scripts_dir",
    "get_sheets_dir",
    "get_sheets_folders_dir",
    "get_sheets_zip_dir",
    # tools
    "get_tool_python",
    "get_video_concat_path",
    "get_video_dir",
    "get_video_frames_dir",
    "get_video_work_dir",
    "list_projects",
    "load_project_metadata",
    "read_manifest",
    "read_remote_chapter_cache",
    "save_project_metadata",
    "update_manifest_chapter",
    "write_remote_chapter_cache",
]
