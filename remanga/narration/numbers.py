"""Digits to spoken words.

A TTS engine handed "3,000" either spells it out digit by digit, reads it in
the wrong language's number grammar, or drops the comma and says something
else entirely - and which of those you get varies by engine, which is worse
than any one of them. Writing "three thousand" into narration.json removes
the question: what the model receives is what it says.

Deliberately no dependency (num2words, inflect): this is a few hundred
values of English number grammar, and a pinned extra package for it would be
a heavier thing to carry than the code."""

from __future__ import annotations

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_SCALES = ((1_000_000_000_000, "trillion"), (1_000_000_000, "billion"),
           (1_000_000, "million"), (1_000, "thousand"))

# Irregular ordinals - everything else is regular enough to derive.
_ORDINAL_WORDS = {
    "one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
    "nine": "ninth", "twelve": "twelfth",
}


def int_to_words(value: int) -> str:
    """123 -> "one hundred twenty-three". Negative and zero included."""
    if value < 0:
        return f"minus {int_to_words(-value)}"
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return f"{_ONES[hundreds]} hundred" + (f" {int_to_words(rest)}" if rest else "")
    for scale, name in _SCALES:
        if value >= scale:
            count, rest = divmod(value, scale)
            return f"{int_to_words(count)} {name}" + (f" {int_to_words(rest)}" if rest else "")
    return str(value)  # unreachable for any int this function is given


def ordinal_to_words(value: int) -> str:
    """3 -> "third", 21 -> "twenty-first". Only the final word changes."""
    words = int_to_words(value)
    head, _, last = words.rpartition("-") if "-" in words.split()[-1] else ("", "", "")
    if last:
        return f"{words[: -len(last)]}{_ordinal_word(last)}"
    prefix, _, final = words.rpartition(" ")
    return (prefix + " " if prefix else "") + _ordinal_word(final)


def _ordinal_word(word: str) -> str:
    if word in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[word]
    if word.endswith("y"):
        return word[:-1] + "ieth"
    return word + "th"


def decimal_to_words(whole: str, fraction: str) -> str:
    """3.5 -> "three point five" - the fractional part is read digit by
    digit, which is how a person says it."""
    digits = " ".join(_ONES[int(d)] for d in fraction)
    return f"{int_to_words(int(whole))} point {digits}"
