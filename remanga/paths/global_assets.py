"""Cross-project shared assets that live under global/ (see roots.GLOBAL_DIR):
currently just the narration-lessons log. Reference voice WAV, BGM file, and
the audio8 TTS transcript path also default under global/ (global/voice/,
global/bgm/, global/tts_reference.txt) but are user-configurable paths in
config.json (remanga/config/tts.py, remanga/config/audio.py) rather than
fixed locations, so they're managed via remanga/paths_manager.py
(`remanga paths`), not fixed getters here."""

from __future__ import annotations

from pathlib import Path

from .roots import GLOBAL_DIR


def get_global_lessons_path() -> Path:
    """One file, shared by every project - not per-chapter or per-manga.
    Accumulates generalized narration mistakes/fixes an LLM has made across
    review rounds (see prompts/narration_review.md), phrased so they're
    useful on any manga, not just the one that surfaced them. Uploaded
    alongside narration.md/narration_review.md on every writing or review
    round so the same class of mistake doesn't recur project to project."""
    p = GLOBAL_DIR / "narration_lessons.json"
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
