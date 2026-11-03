"""Checking an LLM's narration reply against the chapter's panels
(prompts/narration.md is the contract), and the fix request written when it
does not check out: errors stop the video, warnings are the narration style
(reported speech - no quote marks, no contractions) and its pacing. `?`, `!`
and `...` are allowed: the narrator ends a sentence with one where it is a
question, an exclamation or a trailing-off."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

SKIP_REASONS = ("credits", "ad", "blank", "duplicate", "title", "merged", "merged_prev")

# A story panel left out of the video because it has nothing of its own to
# show - only speech bubbles, the same moment held a beat longer - so its
# content is told over a neighbour that does: a panel of bare bubbles on
# screen is dead air. Unlike the other reasons it is still story, so a
# narrated panel has to tell it: the next one (merged), or the one before
# (merged_prev).
MERGED = "merged"
MERGED_PREV = "merged_prev"

# More merged panels than this share of the chapter is the LLM skipping
# story, not folding empty panels into their neighbours.
MAX_MERGED_SHARE = 0.5

# A narrated panel told in more words than this holds one picture on screen
# for 40 seconds or so - the pacing a viewer drifts off at.
MAX_WORDS_PER_PANEL = 110


PANEL_KEYS = ("panel", "skip", "text")


# A panel told in fewer words than this is usually a caption, not the panel
# and everything said in it.
MIN_WORDS_PER_PANEL = 3


_CONTRACTION = re.compile(r"\b\w+(?:n't|'re|'ve|'ll|'d|'m)\b|\b(?:it|that|there|what|he|she|who|here)'s\b",
                          re.IGNORECASE)


class NarrationError(ValueError):
    """The narration can't be used as it is; the message says why and where
    the fix request was written."""


@dataclass
class Check:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _style_warnings(stem: str, text: str) -> list[str]:
    """prompts/narration.md's voice rules that a program can see."""
    found = []
    if re.search(r"[\"“”]", text):
        found.append("quotation marks")
    contractions = sorted({m.group(0) for m in _CONTRACTION.finditer(text)})
    if contractions:
        found.append(f"contractions ({', '.join(contractions[:4])})")
    return [f"{stem}: the narration uses {', '.join(found)} - the voice rules forbid them"] if found else []


def check_reply(doc: Any, panel_stems: list[str], chapter: str) -> Check:
    check = Check()
    if not isinstance(doc, dict) or not isinstance(doc.get("panels"), list):
        check.errors.append('the reply is not a JSON object with a "panels" list')
        return check
    if "chapter" in doc and str(doc["chapter"]).strip().lstrip("0") != str(chapter).strip().lstrip("0"):
        check.warnings.append(f"the reply says chapter {doc['chapter']!r}, but it is chapter {chapter}'s file")
    check.warnings.extend(f"the LLM reported: {problem}" for problem in doc.get("problems") or [])
    if "memory" in doc and not isinstance(doc["memory"], dict):
        check.errors.append('"memory" must be a JSON object, the story so far')

    known, seen, told = set(panel_stems), [], 0
    # Merged panels waiting for a narrated panel to carry them, and how many there were.
    pending_merge: list[str] = []
    merged = 0
    for entry in doc["panels"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("panel"), str):
            check.errors.append(f"an entry in panels has no panel ID: {json.dumps(entry)[:80]}")
            continue
        stem = entry["panel"]
        if stem not in known:
            check.errors.append(f"panel {stem} is not one of this chapter's panels")
            continue
        if stem in seen:
            check.errors.append(f"panel {stem} appears more than once")
            continue
        seen.append(stem)
        skip, text = entry.get("skip"), entry.get("text")
        if skip == MERGED:
            pending_merge.append(stem)
        elif skip == MERGED_PREV:
            if told:
                merged += 1
            else:
                check.errors.append(f"{stem}: merged into the panel before it, but no panel before it is narrated "
                                    f"- tell it in its own text, or merge it into the next one")
        if skip:
            if skip not in SKIP_REASONS:
                check.errors.append(f"{stem}: skip must be one of {', '.join(SKIP_REASONS)} (got {skip!r})")
            if text:
                check.errors.append(f"{stem}: a skipped panel has no narration - its text must be empty")
            continue
        if not isinstance(text, str) or not text.strip():
            check.errors.append(f"{stem}: needs its narration in text, or a skip reason")
            continue
        told += 1
        merged += len(pending_merge)
        pending_merge.clear()
        words = len(text.split())
        if words < MIN_WORDS_PER_PANEL:
            check.warnings.append(f"{stem}: {words} words - is everything in the panel told, with all of its "
                                  f"dialogue")
        elif words > MAX_WORDS_PER_PANEL:
            check.warnings.append(f"{stem}: {words} words on one picture (about {round(words / 2.6)} s on screen) - "
                                  f"keep a panel folded into it as a shot of its own, if there is one")
        check.warnings.extend(_style_warnings(stem, text))
        unknown = sorted(set(entry) - set(PANEL_KEYS))
        if unknown:
            check.warnings.append(f"{stem}: ignored unknown key(s) {', '.join(unknown)}")

    if pending_merge:
        check.errors.append(f"{', '.join(pending_merge)}: merged into the next panel, but no panel after it is "
                            f"narrated - tell it in its own text instead")
    if told and merged > MAX_MERGED_SHARE * (told + merged):
        check.warnings.append(f"{merged} of {told + merged} story panels are merged into a neighbour - only a "
                              f"panel with nothing of its own to show (just bubbles, a moment held) should be")
    missing = [stem for stem in panel_stems if stem not in seen]
    if missing:
        check.errors.append(f"panel(s) missing from panels: {', '.join(missing)}")
    if not missing and not told:
        check.errors.append("every panel is skipped - there is nothing to narrate")
    return check


def fix_request_text(chapter: str, errors: list[str], patch: bool = True) -> str:
    """What to paste back into the same LLM conversation. A reply that reads
    is fixed with a patch - only the panels that change, merged back in by
    narration/document.py - so a two-line fix does not write the chapter
    out again; one that is not JSON at all has to come again whole."""
    if not patch:
        ask = (f"The narration for chapter {chapter} didn't pass the checks. Fix the problems below and reply "
               f"again in full - the one JSON block with both sections, narration (every panel) and memory.")
    else:
        ask = (f"The narration for chapter {chapter} didn't pass the checks. Fix only the problems below, checked "
               f"against the panels, and reply with one JSON block holding only what changes - the panels you "
               f'add or rewrite, keyed by id, and "memory" only if a fix changes it:\n'
               f'{{"patch": {{"chapter": "{chapter}", "panels": {{"PANEL_ID": "its narration, or skip REASON"}}}}}}')
    return "\n".join([ask, "", *[f"- {error}" for error in errors]]) + "\n"
