"""Where page narration reads and writes - declared in its manifest
(generated_kinds, source_files) so wipe, restart and rebuild know about them."""

from __future__ import annotations

from pathlib import Path

from remanga.paths import PROMPTS_DIR, get_chapter_dir, get_generated_dir

PROMPT_PATH = PROMPTS_DIR / "page_narration.md"
# The narration prompt's craft and voice rules, which the page prompt defers to.
NARRATION_PROMPT_PATH = PROMPTS_DIR / "narration.md"
REPLY_FILE = "page_narration.json"
FIX_REQUEST_NAME = "fix_request.md"
PAGE_PANEL_SUFFIX = "_01"


def get_page_upload_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """The chapter's pages as PDF uploads, plus the fix request written when a
    reply doesn't check out."""
    return get_generated_dir(project_name, "page_upload", chapter_num, create=create)


def get_reply_path(project_name: str, chapter_num: str) -> Path:
    """Where the LLM's page narration is pasted. SOURCE, beside narration.json:
    it's an LLM's work, not something remanga can rebuild."""
    return get_chapter_dir(project_name, chapter_num) / REPLY_FILE


def chapter_page_files(project_name: str, chapter_num: str) -> list[Path]:
    """Every file in the chapter's pages/, in order."""
    pages_dir = get_chapter_dir(project_name, chapter_num) / "pages"
    return sorted(p for p in pages_dir.iterdir() if p.is_file()) if pages_dir.exists() else []


def page_panel_id(page_stem: str) -> str:
    """The panel id a whole page gets: its page name as the page's one and
    only panel (`001_014` -> `001_014_01`), in the `{chapter}_{page}_{panel}`
    shape every other panel has."""
    return f"{page_stem}{PAGE_PANEL_SUFFIX}"
