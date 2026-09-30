"""Checking an LLM's narration reply against the chapter's panels
(prompts/narration.md is the contract), and the fix request written when it
does not check out: errors stop the video, warnings are the user's style
(reported speech - no quote marks, no ?/!, no contractions)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

SKIP_REASONS = ("credits", "ad", "blank", "duplicate", "title")


PANEL_KEYS = ("panel", "skip", "text")


# A panel told in fewer words than this is usually a caption, not the panel
# and everything said in it.
MIN_WORDS_PER_PANEL = 5


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
    if "?" in text or "!" in text:
        found.append("a question or exclamation mark")
    if "..." in text or "…" in text:
        found.append("an ellipsis")
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
        if len(text.split()) < MIN_WORDS_PER_PANEL:
            check.warnings.append(f"{stem}: {len(text.split())} words - is everything in the panel told, with all "
                                  f"of its dialogue")
        check.warnings.extend(_style_warnings(stem, text))
        unknown = sorted(set(entry) - set(PANEL_KEYS))
        if unknown:
            check.warnings.append(f"{stem}: ignored unknown key(s) {', '.join(unknown)}")

    missing = [stem for stem in panel_stems if stem not in seen]
    if missing:
        check.errors.append(f"panel(s) missing from panels: {', '.join(missing)}")
    if not missing and not told:
        check.errors.append("every panel is skipped - there is nothing to narrate")
    return check


def fix_request_text(chapter: str, errors: list[str]) -> str:
    """What to paste back into the same LLM conversation."""
    return "\n".join([
        f"The narration for chapter {chapter} didn't pass the checks. Fix only the problems below, checked "
        f"against the panels, and reply again in full - the one JSON block with both sections, narration (every "
        f"panel) and memory - not only what changed.",
        "",
        *[f"- {error}" for error in errors],
    ]) + "\n"
