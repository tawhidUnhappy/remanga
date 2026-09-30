"""The narration the LLM writes for a chapter, pasted into
chapters/chapter_N/narration.json, and everything remanga checks about it.

Its shape is prompts/narration.md's Reply section: one entry per PANEL of the
chapter, in reading order, each with the narration `text` read while that panel
is on screen; a marked panel that isn't story (a credits box, a title) is
skipped with a reason instead. The reply's second section, `memory`, is the
story so far after this chapter, which the next chapter's PDF reads straight
from this file.

A reply that doesn't check out stops the video before anything is
synthesized, and gets a fix request (pdf/chapter_N/fix_request.md) to paste
back into the same LLM conversation.

    files.py     the chapter's page and panel files
    check.py     checking a reply, and the fix request
    document.py  reading, loading and writing narration.json; the story so far"""

from __future__ import annotations

from remanga.narration.check import (
    MIN_WORDS_PER_PANEL,
    PANEL_KEYS,
    SKIP_REASONS,
    Check,
    NarrationError,
    check_reply,
    fix_request_text,
)
from remanga.narration.document import (
    FIX_REQUEST_NAME,
    PROMPT_PATH,
    StoryPanel,
    load_narration,
    narration_document,
    read_reply,
    story_so_far,
    written_panels,
)
from remanga.narration.files import PAGE_IMAGE_EXTS, PANEL_IMAGE_EXTS, page_files, panel_files

__all__ = [
    "FIX_REQUEST_NAME",
    "MIN_WORDS_PER_PANEL",
    "PAGE_IMAGE_EXTS",
    "PANEL_IMAGE_EXTS",
    "PANEL_KEYS",
    "PROMPT_PATH",
    "SKIP_REASONS",
    "Check",
    "NarrationError",
    "StoryPanel",
    "check_reply",
    "fix_request_text",
    "load_narration",
    "narration_document",
    "page_files",
    "panel_files",
    "read_reply",
    "story_so_far",
    "written_panels",
]
