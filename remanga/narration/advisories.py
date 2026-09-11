"""Things worth telling someone about their narration - without changing it.

The normalizer's rules all share a property: the right answer is mechanical.
Everything in this module is the opposite - real problems whose only honest
fix is a human or an LLM rewriting the line, so the command reports them and
stops there.

Each check exists because it was found by hand in a real chapter and would
otherwise have to be re-derived by hand next time.

There is deliberately no length check. prompts/narration.md asks for every
line of dialogue in full and a full explanation of each panel, with no word
ceiling (its Rule 4), so a long line is what a dialogue-heavy panel should
produce - and a panel is held on screen for as long as its own audio runs, so
nothing gets rushed to fit. The old 26-word ceiling check went with the rule
it enforced."""

from __future__ import annotations

import collections
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

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
    examples: list[str]


def advise(entries: Sequence[dict[str, Any]]) -> list[Advisory]:
    """Every advisory that applies to this chapter's narration entries."""
    texts = [(e.get("panel_id", "?"), (e.get("text") or "")) for e in entries]
    if not texts:
        return []

    found: list[Advisory] = []
    for check in (_empty_lines, _duplicate_lines, _repeated_openers):
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
