"""Cross-project shared assets that live under global/ (see roots.GLOBAL_DIR):
the narration-lessons log and the optional HF token file. Reference voice
WAV, BGM file, and the audio8 TTS transcript path also default under
global/ (global/voice/, global/bgm/, global/tts_reference.txt) but are
user-configurable paths in config.json (remanga/config/tts.py,
remanga/config/audio.py) rather than fixed locations, so they're managed
via remanga/settings/ (`remanga paths`), not fixed getters here."""

from __future__ import annotations

import json
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


def get_hf_token_path() -> Path:
    """SystemConfig.hf_token_path's own default target - see remanga/hf_token.py
    for the full contract. A real on-disk default (not just a config.json
    default *value*) so the file - and the place to put a token - exists the
    first time anything downloads a model, without the user having to create
    it or point config.json at anything themselves first."""
    p = GLOBAL_DIR / "hf_token.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def ensure_hf_token_file() -> Path:
    """Creates a placeholder the first time it's needed, never clobbering a
    token already written there. The "_hint" field is just in-file
    documentation (JSON has no comments) pointing at where to actually get a
    token - remanga/hf_token.py only ever reads "token", so its presence
    doesn't affect parsing either way. A blank "token" value is the normal,
    expected "nothing configured yet" state - treated as silently equivalent
    to no file at all, not a warning-worthy misconfiguration."""
    p = get_hf_token_path()
    if not p.exists():
        placeholder = {
            "token": "",
            "_hint": "Optional - paste a Hugging Face access token here (https://huggingface.co/settings/tokens, "
                     "'Read' scope is enough) to raise the Hub's per-IP rate limit/speed on model downloads "
                     "(IndexTTS-2.5, Audio8 TTS, MAGI v3, DeepSeek-OCR-2). Leave \"token\" blank to keep "
                     "downloading unauthenticated - nothing breaks either way.",
        }
        p.write_text(json.dumps(placeholder, indent=2) + "\n", encoding="utf-8")
    return p
