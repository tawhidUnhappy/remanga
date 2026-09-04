"""Making narration text safe to speak.

Two jobs, and they pull against each other, so the split is explicit:

REMOVED - things a TTS engine turns into noise. Emoji and symbols (read as
nothing, as a symbol name, or as a glitch depending on the engine), markdown
the LLM left in (`**like this**`, which gets voiced as "asterisk asterisk"
or swallows the word), URLs, stray brackets, zero-width and control
characters, SHOUTED WORDS (many front-ends spell all-caps out letter by
letter - "SHUT UP" becomes "ess aitch you tee"), streeeetched letters, and
raw digits (each engine reads "3,000" in its own way, and none of them ask).

KEPT - everything that carries delivery. `?`, `!` and `...` are how these
engines infer emotion and pacing when no emotion vector is sent (see
prompts/narration.md Rule 3 and remanga/audio/synth/indextts.py), so they
are never stripped. Runs of them collapse - "!!!" means the same as "!" to a
model and only risks over-reading - and mixed "?!" survives intact, because
that pairing is its own tone. Commas, periods, apostrophes and quotes stay:
they're the phrasing.

Each rule below is a named function, and normalize_text reports which ones
actually fired - so the command can say what it changed rather than handing
back a silently different script."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, List, Tuple

from remanga.narration.delivery import ranks, speech_case, speech_quotes, titles
from remanga.narration.numbers import decimal_to_words, int_to_words, ordinal_to_words

# The complete set of characters allowed to reach the synthesizer. Anything
# else is dropped by the final pass - a whitelist rather than a blocklist,
# because the failure mode of a missed exotic character (a random glitch in
# the middle of a chapter) is worse than the failure mode of dropping one
# (a slightly plainer sentence).
ALLOWED_PUNCTUATION = ".,!?'\"-:;() "
_ALLOWED_RE = re.compile(rf"[^A-Za-z0-9{re.escape(ALLOWED_PUNCTUATION)}]")

# Typographic characters -> their speakable ASCII equivalent.
_TYPOGRAPHIC = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "′": "'", "″": '"', "«": '"', "»": '"',
    "–": ", ", "—": ", ", "‒": ", ", "―": ", ", "−": "-",
    "…": "...", " ": " ", " ": " ", " ": " ", " ": " ",
    "•": " ", "·": " ", "・": " ",
}
_TYPOGRAPHIC_RE = re.compile("|".join(map(re.escape, _TYPOGRAPHIC)))

# Symbols worth saying rather than dropping.
_SYMBOL_WORDS = (
    (re.compile(r"\s*&\s*"), " and "),
    (re.compile(r"(?<=\d)\s*%"), " percent"),
    (re.compile(r"\s*\+\s*"), " plus "),
    (re.compile(r"(?<=\w)\s*@\s*(?=\w)"), " at "),
    (re.compile(r"#\s*(?=\d)"), "number "),
    (re.compile(r"\$\s*(\d[\d,]*)"), r"\1 dollars"),
    (re.compile(r"(?<=\d)\s*°"), " degrees"),
)

_ZERO_WIDTH_RE = re.compile(r"[​-‏⁠﻿­]")
# The trailing character class stops a URL at sentence punctuation instead
# of eating it: "(see https://example.com/x)" must not lose its ")" and
# leave an unbalanced bracket behind.
_URL_RE = re.compile(
    r"\b(?:https?://|www\.)[^\s)\]}>,;]*(?<![.,!?:;])|\b[\w.+-]+@[\w-]+\.[\w.]+\b",
    re.IGNORECASE,
)
_LONE_BRACKET_RE = re.compile(r"\((?=[^()]*$)|(?<=^)[^()]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3}|`+|~{2})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
_MD_LEADING_RE = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|>\s+)")
_ORDINAL_RE = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"(?<![\w.])(\d+)\.(\d+)(?![\w.])")
_INTEGER_RE = re.compile(r"(?<![\w])\d[\d,]*(?![\w])")
_SHOUT_RE = re.compile(r"\b[A-Z]{2,}(?:'[A-Z]+)?\b")
_STRETCHED_RE = re.compile(r"(\w)\1{3,}", re.IGNORECASE)
_EMPTY_BRACKETS_RE = re.compile(r"\(\s*\)")


@dataclass(frozen=True)
class Rule:
    """One normalization step. `summary` is what the command prints when
    this rule actually changed something."""

    name: str
    summary: str
    apply: Callable[[str], str]


def _unicode_form(text: str) -> str:
    """NFKC folds fullwidth/compatibility forms (ｈｅｌｌｏ, ﬁ) into plain
    letters, then control and zero-width characters go - they're invisible in
    an editor and can split a word mid-token for the model."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C"))


def _typographic(text: str) -> str:
    """Smart quotes, dashes and the ellipsis character -> ASCII. The
    ellipsis becomes "..." rather than vanishing: it's a pause the engine
    actually performs.

    A dash at the very end ("What the-") is an interrupted line, not a
    clause break, so it becomes "..." - which is the pause a reader hears
    there. Turning it into a comma would leave ", ." once the sentence-end
    rule ran."""
    text = re.sub(r"\s*[-\u2012-\u2015\u2212]+\s*(?=[\"\')\]]*$)", "...", text)
    return _TYPOGRAPHIC_RE.sub(lambda m: _TYPOGRAPHIC[m.group()], text)


def _markup(text: str) -> str:
    """Markdown an LLM left behind. The text inside is kept; only the
    marks go."""
    text = _MD_LEADING_RE.sub("", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    for _ in range(3):  # nested emphasis (**_word_**)
        new = _MD_EMPHASIS_RE.sub(r"\2", text)
        if new == text:
            break
        text = new
    return text


# A bracketed group containing a link is a citation - "(see https://...)" -
# and none of it is meant to be spoken. Removing the whole group avoids the
# "(see )" stub that stripping just the URL would leave behind.
_BRACKETED_URL_RE = re.compile(r"[(\[][^)\]]*(?:https?://|www\.)[^)\]]*[)\]]", re.IGNORECASE)


def _urls(text: str) -> str:
    text = _BRACKETED_URL_RE.sub(" ", text)
    return _URL_RE.sub(" ", text)


def _symbols(text: str) -> str:
    for pattern, replacement in _SYMBOL_WORDS:
        text = pattern.sub(replacement, text)
    return text


def _numbers(text: str) -> str:
    """Digits -> words, so every engine says the same thing. Ordinals and
    decimals first, since the integer rule would otherwise eat their
    digits."""
    text = _ORDINAL_RE.sub(lambda m: ordinal_to_words(int(m.group(1))), text)
    text = _DECIMAL_RE.sub(lambda m: decimal_to_words(m.group(1), m.group(2)), text)
    return _INTEGER_RE.sub(lambda m: int_to_words(int(m.group().replace(",", ""))), text)


def _shouting(text: str) -> str:
    """ALL-CAPS words -> normal case, keeping the first letter capitalized.

    Emphasis written as capitals is not emphasis to a TTS front-end: it's a
    likely acronym, and the common ones spell it out letter by letter. The
    exclamation mark that almost always accompanies shouting still carries
    the delivery, and that is left alone. Single capitals ("A rank", "S
    class") are untouched - they really are letters.

    Case follows position: a shout that starts a sentence keeps its capital,
    one in the middle of a sentence becomes lowercase, so "he SCREAMS" reads
    as "he screams" rather than "he Screams"."""

    def replace(match: re.Match) -> str:
        word = match.group().lower()
        before = text[: match.start()].rstrip()
        if not before or before[-1] in ".!?:":
            return word.capitalize()
        return word

    return _SHOUT_RE.sub(replace, text)


def _stretched(text: str) -> str:
    """"Nooooooo" -> "Nooo". The stretch reads as emphasis to a human and as
    an unpronounceable token to a model; three keeps the intent."""
    return _STRETCHED_RE.sub(lambda m: m.group(1) * 3, text)


def _punctuation(text: str) -> str:
    """Collapse repeated marks, drop leftover bracket characters, and fix
    spacing around punctuation.

    "?" and "!" are never removed here - only de-duplicated ("!!!" -> "!"),
    and a mixed "?!" is preserved as its own tone. "..." is preserved and
    normalized to exactly three dots."""
    text = re.sub(r"\.{3,}", "...", text)
    text = re.sub(r"([!?])\1{1,}", r"\1", text)
    text = re.sub(r"([,;:])[,;:]+", r"\1", text)
    text = _EMPTY_BRACKETS_RE.sub(" ", text)
    text = _LONE_BRACKET_RE.sub(" ", text)               # bracket left unpaired by a removal
    text = re.sub(r"([,;:])\s*(?=[,;:])", "", text)      # ", ," from a removed clause
    text = re.sub(r",\s*(?=[.!?])", "", text)            # ", ." -> "."
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)          # no space before punctuation
    text = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", text)   # space after it
    text = re.sub(r"([.!?])(?=[A-Za-z])", r"\1 ", text)
    text = re.sub(r"(?<!\.)\.(?=\.\.)", ".", text)
    text = re.sub(r"\s*-\s*$", "...", text)               # "What the-" -> a trailing pause
    return text


def _charset(text: str) -> str:
    """The whitelist: anything that isn't a letter, digit, space or
    speakable punctuation is dropped. This is what catches emoji, box
    drawing, arrows, CJK punctuation and every other character that reaches
    a synthesizer as a glitch."""
    return _ALLOWED_RE.sub(" ", text)


def _whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sentence_end(text: str) -> str:
    """Give the line a terminal mark if it has none. Engines lean on it for
    final-phrase prosody; without one the last words trail off flat or run
    into the next panel's clip."""
    if not text:
        return text
    if text[-1] in ".!?":
        return text
    if text[-1] in "'\")" and len(text) > 1:
        if text[-2] in ".!?":
            return text
        # "she whispers, 'it is over'" -> the mark goes inside the quote,
        # where a writer would have put it and where it reads as the end of
        # the spoken line rather than an extra beat after it.
        return text[:-1] + "." + text[-1]
    return text + "."


# Safety first (what would glitch), then delivery (what would read flat).
# Delivery rules run last, on text that's already clean, so they never have
# to reason about emoji or markdown - see remanga/narration/delivery.py.
RULES: Tuple[Rule, ...] = (
    Rule("unicode", "normalized unicode / removed invisible characters", _unicode_form),
    Rule("typographic", "converted smart quotes, dashes and ellipses", _typographic),
    Rule("markup", "removed leftover markdown", _markup),
    Rule("urls", "removed URLs and email addresses", _urls),
    Rule("symbols", "spelled out symbols (&, %, $, +)", _symbols),
    Rule("numbers", "wrote digits out as words", _numbers),
    Rule("shouting", "un-SHOUTED all-caps words", _shouting),
    Rule("stretched", "shortened streeetched letters", _stretched),
    Rule("charset", "removed emoji and unspeakable characters", _charset),
    Rule("punctuation", "tidied punctuation (kept ? ! ...)", _punctuation),
    Rule("whitespace", "collapsed whitespace", _whitespace),
    Rule("sentence_end", "added a missing sentence ending", _sentence_end),
    Rule("speech_quotes", "used double quotes for speech (freeing ' for apostrophes)", speech_quotes),
    Rule("speech_case", "capitalized the start of quoted speech", speech_case),
    Rule("titles", "spelled out titles (Mr. -> Mister)", titles),
    Rule("ranks", "hyphenated A rank / S class", ranks),
)

RULE_BY_NAME = {rule.name: rule for rule in RULES}


def normalize_text(text: str) -> Tuple[str, List[str]]:
    """Returns the speakable text plus the names of the rules that actually
    changed something, in the order they ran. Idempotent: normalizing
    already-normalized text returns it unchanged with an empty rule list."""
    applied: List[str] = []
    for rule in RULES:
        after = rule.apply(text)
        if after != text:
            applied.append(rule.name)
            text = after
    return text, applied
