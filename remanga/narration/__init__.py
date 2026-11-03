"""The narration the LLM writes for a chapter, pasted into
chapters/chapter_N/narration.json, and everything remanga checks about it.

Its shape is prompts/narration.md's Reply section: every PANEL of the
chapter, in reading order, keyed by its id, with the narration read while that
panel is on screen; a marked panel that isn't story (a credits box, a title) is
skipped with a reason instead, and a story panel with nothing of its own to
show is merged - its content told over the next narrated panel or the one
before. The reply's second section, `memory`, is what the chapter changed in
the story; the next chapter's PDF folds every earlier chapter's into the story
so far, straight from their files.

A reply that doesn't check out stops the video before anything is
synthesized, and gets a fix request (pdf/chapter_N/fix_request.md) to paste
back into the same LLM conversation; its answer is a patch, merged back in.

    files.py     the chapter's page and panel files
    check.py     checking a reply, and the fix request
    document.py  reading, loading and writing narration.json; patches; the story so far
    story.py     every chapter's memory folded into the story so far"""

from __future__ import annotations

from remanga.narration.check import (
    MAX_WORDS_PER_PANEL,
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
    keep_base,
    load_narration,
    narration_document,
    panel_entries,
    read_reply,
    story_so_far,
    written_panels,
)
from remanga.narration.files import PAGE_IMAGE_EXTS, PANEL_IMAGE_EXTS, page_files, panel_files
from remanga.narration.story import Story, memory_problems, story_lines

__all__ = [
    "FIX_REQUEST_NAME",
    "MAX_WORDS_PER_PANEL",
    "MIN_WORDS_PER_PANEL",
    "PAGE_IMAGE_EXTS",
    "PANEL_IMAGE_EXTS",
    "PANEL_KEYS",
    "PROMPT_PATH",
    "SKIP_REASONS",
    "Check",
    "NarrationError",
    "Story",
    "StoryPanel",
    "check_reply",
    "fix_request_text",
    "keep_base",
    "load_narration",
    "memory_problems",
    "narration_document",
    "page_files",
    "panel_entries",
    "panel_files",
    "read_reply",
    "story_lines",
    "story_so_far",
    "written_panels",
]
