"""narration.json: its shape, creating one, and making its text safe to speak.

    document.py   - the document shape, the two ways to create the file, and
                    the normalize/save orchestration
    normalize.py  - the safety rules (what gets removed, what is kept)
    delivery.py   - the rules that change how a line is performed
    numbers.py    - digits to spoken words
    advisories.py - what's wrong but not mechanically fixable, reported only

Split because the rules are the part worth reading on their own: what a
normalizer strips from someone's narration script is a decision, not an
implementation detail."""

from __future__ import annotations

from remanga.narration.advisories import Advisory, advise
from remanga.narration.document import (
    BLANK, NARRATION_FILE_MODES, NARRATION_FILE_MODE_BY_NAME, NARRATION_FILE_MODE_NAMES,
    PANEL_IMAGE_EXTS, TEMPLATE, NarrationFileMode, PanelChange, create_narration_file,
    narration_document, narration_path, normalize_narration, panel_ids, save_narration,
)
from remanga.narration.normalize import ALLOWED_PUNCTUATION, RULES, RULE_BY_NAME, normalize_text

__all__ = [
    "ALLOWED_PUNCTUATION",
    "Advisory",
    "advise",
    "BLANK",
    "NARRATION_FILE_MODES",
    "NARRATION_FILE_MODE_BY_NAME",
    "NARRATION_FILE_MODE_NAMES",
    "NarrationFileMode",
    "PANEL_IMAGE_EXTS",
    "PanelChange",
    "RULES",
    "RULE_BY_NAME",
    "TEMPLATE",
    "create_narration_file",
    "narration_document",
    "narration_path",
    "normalize_narration",
    "normalize_text",
    "panel_ids",
    "save_narration",
]
