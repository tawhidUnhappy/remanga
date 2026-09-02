"""Deterministic TTS-safety normalization for narration text - the code-level
enforcement of prompts/narration.md Rule 5's "raw dialogue, TTS-safe" bullet.

That prompt rule asks the narration LLM to keep dialogue verbatim except for
stripping manga lettering's own stutter/trailing-off typography (hyphens,
ellipses: "w-what", "I...was"), because narration.json text goes straight into
IndexTTS-2.5/audio8 synthesis with no normalization of its own. Prompt
compliance is never guaranteed, though - an LLM can still emit "w-what"
despite the instruction, and by the time that reaches narration.json it's
already committed to disk waiting for someone to notice by hand. This module
is the actual guarantee: TTSEngine.generate_narration_audio() (audio/tts.py)
runs every panel's text through normalize_for_tts() right before it's handed
to the synthesizer, so a stray stutter/ellipsis never reaches audio no matter
what the LLM produced. The prompt rule stays as the cheap first pass (better
output, less for this module to fix); this is the backstop.
"""

from __future__ import annotations

import re

# Sequences of 2+ literal dots, or the single "…" character - never a lone
# "." (that's just a sentence/abbreviation period, e.g. "Mr." or "3.5", and
# must be left alone).
_ELLIPSIS_RE = re.compile(r"\s*(?:\.{2,}|…)\s*")

_MULTISPACE_RE = re.compile(r" {2,}")

# A leading 1-2 letter stutter syllable followed by a hyphen, repeated up to
# 3x ("w-", "t-t-", "d-d-d-"), immediately before the real word. Longer
# hyphenated prefixes ("well-", "self-") are never stutters - real
# hyphenated compound words stay well clear of this 1-2 letter cap, which is
# what keeps this from mangling e.g. "well-known" or "self-aware".
_STUTTER_RE = re.compile(r"\b(?:[A-Za-z]{1,2}-){1,3}([A-Za-z]+)\b")


def _destutter(match: "re.Match[str]") -> str:
    """Only fires if every hyphenated prefix syllable is actually a case-
    insensitive prefix of the word that follows it (the real stutter
    pattern) - anything else matching the regex shape but failing that check
    is left untouched rather than guessed at."""
    word = match.group(1)
    prefixes = match.group(0)[: -len(word)].split("-")[:-1]
    if all(word.lower().startswith(p.lower()) for p in prefixes if p):
        return word
    return match.group(0)


def normalize_for_tts(text: str) -> str:
    """Strips manga lettering's stutter/trailing-off typography from `text`
    without touching actual wording - see module docstring. Idempotent and
    safe to call on text that's already clean (the common case, when the LLM
    followed the prompt rule)."""
    if not text:
        return text

    text = _ELLIPSIS_RE.sub(" ", text)
    text = _STUTTER_RE.sub(_destutter, text)
    text = _MULTISPACE_RE.sub(" ", text)
    return text.strip()
