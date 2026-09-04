"""Things worth telling someone about their narration - without changing it.

The normalizer's rules all share a property: the right answer is mechanical.
Everything in this module is the opposite - real problems whose only honest
fix is a human or an LLM rewriting the line, so the command reports them and
stops there.

Each check exists because it was found by hand in a real chapter and would
otherwise have to be re-derived by hand next time. The thresholds are the
project's own: the word ceiling is prompts/narration.md Rule 4's, not a
number invented here."""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

# prompts/narration.md Rule 4: "Never exceed 26 words on any single panel"
# (~3.5-5.0s of audio at the 10-20 word target).
WORD_CEILING = 26

# Share of lines opening with an "-ing" participle ("Clutching his chest,
# ...", "Flashing a smirk, ...") above which the script starts to sound like
# one repeated sentence shape read 129 times. Set from a measured chapter
# that was at 45% and audibly monotonous; a third is a comfortable ceiling.
PARTICIPIAL_SHARE = 0.35

_PARTICIPIAL = re.compile(r"^[A-Z][a-z]+ing\b")


@dataclass(frozen=True)
class Advisory:
    """One observation the command reports but never acts on. `fix` says what
    a person would actually do about it."""

    name: str
    message: str
    fix: str
    examples: List[str]


def advise(entries: Sequence[Dict[str, Any]]) -> List[Advisory]:
    """Every advisory that applies to this chapter's narration entries."""
    texts = [(e.get("panel_id", "?"), (e.get("text") or "")) for e in entries]
    if not texts:
        return []

    found: List[Advisory] = []
    for check in (_empty_lines, _over_word_ceiling, _duplicate_lines, _repeated_openers):
        advisory = check(texts)
        if advisory is not None:
            found.append(advisory)
    return found


def _empty_lines(texts):
    empty = [pid for pid, text in texts if not text.strip()]
    if not empty:
        return None
    return Advisory(
        "empty_lines",
        f"{len(empty)} panel(s) have no narration at all",
        "Rule 4 says an empty text is never valid - every panel gets a real line, "
        "however short. Write them in the Narration Writer, or regenerate the chapter.",
        empty[:6],
    )


def _over_word_ceiling(texts):
    long_lines = [(pid, text) for pid, text in texts if len(text.split()) > WORD_CEILING]
    if not long_lines:
        return None
    return Advisory(
        "word_ceiling",
        f"{len(long_lines)} line(s) exceed the {WORD_CEILING}-word ceiling",
        "Rule 4's ceiling is about audio length - a longer line is read faster to fit its "
        "panel, or overruns it. Split the thought or cut the scene-setting the art already shows.",
        [f"{pid}: {len(text.split())} words - {text[:70]}..." for pid, text in long_lines[:4]],
    )


def _duplicate_lines(texts):
    counts = collections.Counter(text.strip().casefold() for _, text in texts if text.strip())
    repeated = [text for text, count in counts.items() if count > 1]
    if not repeated:
        return None
    return Advisory(
        "duplicate_lines",
        f"{len(repeated)} line(s) of narration are used on more than one panel",
        "Identical narration on two panels is almost always a generation slip - the viewer "
        "hears the same sentence twice. Rewrite one of them for what its panel actually shows.",
        [text[:70] + "..." for text in repeated[:4]],
    )


def _repeated_openers(texts):
    """The one that doesn't announce itself in any single line: nearly every
    sentence built as "Verb-ing something, X does Y". Each line reads fine
    alone; a chapter of them is a drone."""
    participial = [(pid, text) for pid, text in texts if _PARTICIPIAL.match(text)]
    share = len(participial) / len(texts)
    if share < PARTICIPIAL_SHARE:
        return None
    return Advisory(
        "repeated_openers",
        f"{len(participial)} of {len(texts)} lines ({share:.0%}) open with an '-ing' phrase",
        "Each line reads fine on its own, but one sentence shape repeated for a whole chapter "
        "sounds like a drone however well it's synthesized. Vary the openings when rewriting or "
        "regenerating - the narration prompt asks for this too.",
        [f"{pid}: {text[:60]}..." for pid, text in participial[:4]],
    )
