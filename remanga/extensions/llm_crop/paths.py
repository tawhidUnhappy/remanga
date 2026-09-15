"""Where the LLM crop extension reads and writes - built on remanga.paths, and
declared in its manifest (generated_kinds, source_files) so every wipe,
restart and rebuild already knows about them."""

from __future__ import annotations

from pathlib import Path

from remanga.paths import PROMPTS_DIR, get_chapter_dir, get_generated_dir

PROMPT_PATH = PROMPTS_DIR / "llm_crop.md"
REPLY_FILE = "llm_crops.json"


def get_grid_pages_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "grid_pages", chapter_num, create=create)


def get_grid_zip_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "grid_zip", chapter_num, create=create)


def get_grid_pdf_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    return get_generated_dir(project_name, "grid_pdf", chapter_num, create=create)


def get_llm_crop_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """What importing Gemini's crops generates for a chapter: the preview
    overlays, and the fix request written when a reply doesn't check out."""
    return get_generated_dir(project_name, "llm_crop", chapter_num, create=create)


def get_llm_crops_path(project_name: str, chapter_num: str) -> Path:
    """Where Gemini's reply for a chapter is pasted. SOURCE, beside
    crops.json: it's an LLM's work, not something remanga can rebuild."""
    return get_chapter_dir(project_name, chapter_num) / REPLY_FILE
