"""Putting the narration remanga asked for and the words whisper heard into
the same shape, so they can be matched at all.

The two sides disagree in ways that mean nothing: case, punctuation, hyphens,
and - the one that actually bites - numbers. The narration prompt asks the
LLM to write numbers as words, which settles it going forward, but a chapter
narrated before that still holds digits and whisper writes digits whenever it
feels like it. Normalizing BOTH sides through the same function is simpler
than deciding which side to convert, and it is right no matter which of them
used the digit."""

from __future__ import annotations

import re

_UNITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
          "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
          "seventeen", "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

_WORD_RE = re.compile(r"[a-z0-9']+")
_DIGITS_RE = re.compile(r"\d+")


def _under_hundred(value: int) -> list[str]:
    if value < 20:
        return [_UNITS[value]]
    tens, unit = divmod(value, 10)
    return [_TENS[tens]] if unit == 0 else [_TENS[tens], _UNITS[unit]]


def number_words(value: int) -> list[str]:
    """`value` as the words it is read as. Only what narration actually
    holds: counts, ages, small quantities. A number too big to be read as one
    of those is left as its digits rather than guessed at - it will not match
    either way, and one unmatched token is cheaper than a wrong one."""
    if value < 0 or value > 9999:
        return [str(value)]
    if value < 100:
        return _under_hundred(value)
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        words = [_UNITS[hundreds], "hundred"]
        return words if rest == 0 else words + _under_hundred(rest)
    thousands, rest = divmod(value, 1000)
    words = [_UNITS[thousands], "thousand"]
    return words if rest == 0 else words + number_words(rest)


def words(text: str) -> list[str]:
    """`text` as the sequence of words it would be read as: lower case, no
    punctuation, hyphens split, digits spelled out."""
    lowered = text.lower().replace("-", " ").replace("’", "'")
    out: list[str] = []
    for token in _WORD_RE.findall(lowered):
        if token.isdigit():
            out.extend(number_words(int(token)))
        elif _DIGITS_RE.search(token):
            # "1st", "2nd" - the digits are what carries, the suffix is noise
            out.extend(number_words(int(_DIGITS_RE.search(token).group())))
        else:
            out.append(token.strip("'"))
    return [w for w in out if w]
