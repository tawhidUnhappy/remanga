"""Rules that change how a line is *performed*, not whether it's safe.

remanga/narration/normalize.py removes what makes a synthesizer glitch.
These are the other half: text that a TTS engine can pronounce perfectly
well but delivers flatly or ambiguously, where a small rewrite gets a better
read out of the same words.

Nothing here changes meaning or word order - the narration stays exactly the
script that was written. Every rule is previewed line by line before it's
written, like every other change to narration.json."""

from __future__ import annotations

import re

# An apostrophe has letters on BOTH sides ("King's", "didn't"). Every other
# single quote is being used as a speech mark. That one distinction is what
# makes the conversion below safe to do automatically.
_APOSTROPHE = re.compile(r"(?<=[A-Za-z])'(?=[A-Za-z])")
_APOSTROPHE_PLACEHOLDER = "\x00"

# An OPENING quote is preceded by a space (or starts the line) and followed
# immediately by the word. A closing quote is preceded by a non-space -
# without that distinction, `"Shut up already," as the blacksmith...` gets
# its "as" capitalized too, which is the narration, not the speech.
_SPEECH_START = re.compile(r'(?:(?<=\s)|^)(")([a-z])')

# Titles a front-end may read as letters ("em ar") rather than as the word.
_TITLES = (
    (re.compile(r"\bMr\.\s*"), "Mister "),
    (re.compile(r"\bMrs\.\s*"), "Missus "),
    (re.compile(r"\bMs\.\s*"), "Miss "),
    (re.compile(r"\bDr\.\s*"), "Doctor "),
    (re.compile(r"\bSt\.\s*"), "Saint "),
)

# "the A rank party" reads as the article "a" unless it's hyphenated, which
# is how the term is normally written anyway. Only uppercase letters match,
# so an ordinary "a rank" is untouched.
_RANK = re.compile(r"\b([A-FS])[ ](rank|class|tier)\b")


def speech_quotes(text: str) -> str:
    """Single-quoted speech -> double quotes.

    A tokenizer sees the same character in "Dragon King's Flame" and in
    "sneers, 'a worthless skill'", and has to guess which is which - 24 of
    this chapter's lines contain both. Double quotes for speech remove the
    guess entirely, and leave the apostrophes as the only single quotes in
    the file."""
    protected = _APOSTROPHE.sub(_APOSTROPHE_PLACEHOLDER, text)
    protected = protected.replace("'", '"')
    return protected.replace(_APOSTROPHE_PLACEHOLDER, "'")


def speech_case(text: str) -> str:
    """Capitalize the first word of quoted speech.

    A quote opening lowercase mid-sentence reads to the model as the middle
    of a clause, and gets that flat continuation prosody. Capitalized, it
    starts a fresh utterance - which is what it is, and how the line is
    punctuated everywhere else."""
    return _SPEECH_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def titles(text: str) -> str:
    return _apply_all(_TITLES, text)


def ranks(text: str) -> str:
    return _RANK.sub(r"\1-\2", text)


def _apply_all(rules, text: str) -> str:
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text
