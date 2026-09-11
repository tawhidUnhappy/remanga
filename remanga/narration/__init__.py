"""narration.json: its shape, and creating one.

    document.py - the document shape, and the two ways to create the file

Making the text itself speakable is the narration LLM's job, not code's: see
the <writing_for_the_voice> section of prompts/narration.md. The
normalize-narration command that used to rewrite it afterwards lives on the
legacy/normalize-narration branch."""

from __future__ import annotations

from remanga.narration.document import (
    BLANK,
    NARRATION_FILE_MODE_BY_NAME,
    NARRATION_FILE_MODE_NAMES,
    NARRATION_FILE_MODES,
    PANEL_IMAGE_EXTS,
    TEMPLATE,
    NarrationFileMode,
    create_narration_file,
    narration_document,
    narration_path,
    panel_ids,
)

__all__ = [
    "BLANK",
    "NARRATION_FILE_MODES",
    "NARRATION_FILE_MODE_BY_NAME",
    "NARRATION_FILE_MODE_NAMES",
    "PANEL_IMAGE_EXTS",
    "TEMPLATE",
    "NarrationFileMode",
    "create_narration_file",
    "narration_document",
    "narration_path",
    "panel_ids",
]
