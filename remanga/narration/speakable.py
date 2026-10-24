"""The narration as a voice can read it: every character a narrator engine
can say kept, the rest taken out.

Narration comes from an LLM reading manga, so now and then it carries what
no engine can voice - a ★ or ♪ copied off the page, an emoji, a name left in
Japanese, full-width ！？ - and an engine meets those by reading them out
letter by letter, guessing, or going silent mid-sentence. Every engine gets
its text through `speakable` (audio/synth/base.py), so narration.json stays
what the LLM wrote and only what is spoken is cleaned.

Kept: plain letters, digits, and the punctuation an engine voices -
. , ; : ? ! ... ' " ( ) - and the em dash. Accents are folded (Chloé ->
Chloe): Ming read "Chloé meets him at the café" as "Khlo meets him at the
CAF", while Kokoro says the folded words the same. Money and fractions are
written out, since the engines read them differently: "$5 and 30 percent"
came back from Ming as "$5.30", and Kokoro read 3/4 as "three-four".
`?`, `!` and `...` carry the delivery (the narrator rises, punches or trails
off - prompts/narration.md), so they stay, but a run of them collapses to
one: "!!!" reads like "!", and some engines stumble on the run."""

from __future__ import annotations

import re
import unicodedata

# Said as words rather than dropped: what they mean is part of the sentence.
_AS_WORDS = {"&": " and ", "%": " percent", "+": " plus ", "=": " equals ", "@": " at "}

# Same mark, another spelling - after NFKC, which already turns full-width
# ！？ into !? and … into ...
_SAME_MARK = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "`": "'", "´": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "–": "—", "‒": "—", "―": "—", "−": "-",
    "¡": "", "¿": "",
    "~": " ", "_": " ", "/": " ", "\\": " ", "|": " ",
    "[": "(", "]": ")", "{": "(", "}": ")",
    "【": "(", "】": ")", "「": "", "」": "", "『": "", "』": "",
    "\n": " ", "\t": " ",
})

# Latin letters that don't decompose into a plain letter and an accent.
_FOLD = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe", "ø": "o", "Ø": "O",
                       "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "þ": "th", "Þ": "Th", "ð": "d", "ı": "i"})

_PUNCTUATION = set(".,;:?!'\"()-—")


def _keeps(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == " ") or char in _PUNCTUATION


def _fold_accents(text: str) -> str:
    """é -> e, ñ -> n: the accent dropped, the letter kept. Only Latin letters
    lose theirs - anything else is left for _keeps to judge."""
    out = []
    for char in unicodedata.normalize("NFD", text.translate(_FOLD)):
        if unicodedata.combining(char) and out and out[-1].isascii():
            continue
        out.append(char)
    return unicodedata.normalize("NFC", "".join(out))


def speakable(text: str) -> str:
    """`text` with only what a narrator engine can say in it."""
    text = _fold_accents(unicodedata.normalize("NFKC", text))
    # $5 -> 5 dollars, 3/4 -> 3 out of 4; then the rest of the slashes are spaces.
    text = re.sub(r"\$\s?(\d[\d,]*(?:\.\d+)?)", r"\1 dollars", text)
    text = re.sub(r"(?<=\d)\s?/\s?(?=\d)", " out of ", text)
    text = text.translate(_SAME_MARK)
    for symbol, words in _AS_WORDS.items():
        text = text.replace(symbol, words)
    text = "".join(char if _keeps(char) else " " for char in text)
    text = re.sub(r"-{2,}", "—", text)
    # A run of marks is one mark: "?!?!" -> "?!", "!!!" -> "!", "....." -> "...".
    text = re.sub(r"[?!]{2,}", lambda m: ("?!" if "?" in m.group() and "!" in m.group() else m.group()[0]),
                  text)
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"[,;:]{2,}", lambda m: m.group()[0], text)
    # What dropping left behind: empty brackets and quotes, spaces before a mark.
    text = re.sub(r"\(\s*\)|\"\s*\"", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,;:?!)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return text.strip()
