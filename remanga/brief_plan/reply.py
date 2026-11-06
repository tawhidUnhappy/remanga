"""An LLM's brief reply - one JSON block - read and checked on its own terms
(the network checks - does the manga exist, has it those chapters - are
workflow/brief.py's). Every mistake found is listed at once, and written as a
fix request to paste back into the same chat, as the upload reply's are."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from remanga.json_io import json_from_reply

BRIEF_REPLY_NAME = "brief_reply.txt"
FIX_REQUEST_NAME = "brief_fix_request.md"

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
CHAPTER = re.compile(r"\d+(?:\.\d+)?")
NAME = re.compile(r"[a-z][a-z0-9_]{2,39}")
CUE_MIN, CUE_MAX = 20, 200
MAX_CANDIDATES = 3
SEED_MAX = 99999


class BriefReplyError(ValueError):
    """A reply that was not used - nothing changed. `errors` are what to fix."""

    def __init__(self, message: str, errors: list[str]):
        super().__init__(message)
        self.errors = errors


@dataclass
class Candidate:
    title: str
    manga_id: str
    why: str = ""


@dataclass
class VoicePlan:
    name: str
    label: str
    cue: str
    seed: int
    use: str
    why: str = ""


@dataclass
class BriefPlan:
    candidates: list[Candidate]
    first: str                     # the chapter the first season starts at, as written ("1", "12.5")
    voice: VoicePlan
    warnings: list[str] = field(default_factory=list)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def read_brief_reply(raw: str, taken_names: set[str] = frozenset()) -> BriefPlan:
    """The reply's plan, or BriefReplyError listing every mistake. `taken_names`
    are voice names already in code - a designed voice may not reuse one."""
    try:
        data = json_from_reply(raw)
    except json.JSONDecodeError as error:
        raise BriefReplyError("The reply is not JSON.", [f"not valid JSON ({error}) - reply with exactly one JSON "
                                                        "block as prompts/brief.md shows"]) from error
    if not isinstance(data, dict):
        raise BriefReplyError("The reply is not a JSON object.", ["the reply must be one JSON object"])

    errors: list[str] = []
    warnings: list[str] = []

    candidates: list[Candidate] = []
    listed = data.get("manga")
    if not isinstance(listed, list) or not listed:
        errors.append('"manga" must be a list of 1-3 candidates, best first: {"title", "mangadex_id", "why"}')
        listed = []
    if len(listed) > MAX_CANDIDATES:
        warnings.append(f'"manga" has {len(listed)} candidates - only the first {MAX_CANDIDATES} are tried')
    for i, entry in enumerate(listed[:MAX_CANDIDATES], 1):
        if not isinstance(entry, dict):
            errors.append(f'manga[{i}] must be an object with "title" and "mangadex_id"')
            continue
        found = UUID.search(_text(entry.get("mangadex_id")) or _text(entry.get("mangadex_url")))
        title = _text(entry.get("title"))
        if not found:
            errors.append(f'manga[{i}] ("{title}"): "mangadex_id" must be the title\'s MangaDex id (36 characters, '
                          'from mangadex.org/title/<id>) or its full link - never a guess; if you cannot see MangaDex '
                          'for real, say so in "notes" and leave this manga out')
            continue
        if not title:
            errors.append(f'manga[{i}]: "title" is missing')
            continue
        candidates.append(Candidate(title, found.group(0).lower(), _text(entry.get("why"))))

    chapters = data.get("chapters")
    first = ""
    if not isinstance(chapters, dict):
        errors.append('"chapters" must be {"from": "1"} - the chapter the first season starts at')
    else:
        first = str(chapters.get("from", "")).strip()
        if not CHAPTER.fullmatch(first):
            errors.append(f'chapters.from must be a chapter number such as "1" or "12.5", not "{first}"')
        if str(chapters.get("to", "")).strip():
            warnings.append('chapters.to is not used - remanga takes one season (12 chapters) from chapters.from')

    voice_data = data.get("voice")
    voice = None
    if not isinstance(voice_data, dict):
        errors.append('"voice" must be {"name", "label", "cue", "seed", "use", "why"}')
    else:
        before = len(errors)
        name, cue = _text(voice_data.get("name")), _text(voice_data.get("cue"))
        label, use = _text(voice_data.get("label")), _text(voice_data.get("use"))
        seed = voice_data.get("seed", 1)
        if not NAME.fullmatch(name):
            errors.append(f'voice.name "{name}" must be lower-case letters, digits and underscores, starting with '
                          'a letter (3-40 characters), e.g. "cold_velvet_narrator"')
        elif name in taken_names or name == "model":
            errors.append(f'voice.name "{name}" is already a voice - give the new one a name of its own')
        if not (cue.startswith("[") and cue.endswith("]") and CUE_MIN <= len(cue) <= CUE_MAX):
            errors.append(f"voice.cue must be one description in square brackets, {CUE_MIN}-{CUE_MAX} characters, "
                          f'e.g. "[rich, warm young male narrator, smooth with clear diction]"; got "{cue}"')
        elif cue.count("[") != 1 or cue.count("]") != 1:
            errors.append("voice.cue must hold exactly one pair of square brackets")
        if not label or len(label) > 40:
            errors.append('voice.label must be a short menu name (1-40 characters), e.g. "Cold velvet narrator"')
        if not use or len(use) > 60:
            errors.append('voice.use must be a few words on how it sounds (1-60 characters)')
        if isinstance(seed, bool) or not isinstance(seed, int) or not 1 <= seed <= SEED_MAX:
            errors.append(f'voice.seed must be a whole number from 1 to {SEED_MAX}')
        if len(errors) == before:
            voice = VoicePlan(name, label, cue, seed, use, _text(voice_data.get("why")))

    if errors:
        raise BriefReplyError(f"The reply has {len(errors)} mistake(s).", errors)
    return BriefPlan(candidates, first, voice, warnings)


def fix_request_text(errors: list[str]) -> str:
    lines = "\n".join(f"- {e}" for e in errors)
    return ("Your reply to the brief could not be used. Fix exactly these and reply again with the whole "
            f"corrected JSON in one block, nothing else:\n\n{lines}\n")
