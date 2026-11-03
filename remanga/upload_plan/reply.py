"""An LLM's upload reply - JSON, pasted into upload/upload_reply.txt - read and
checked against the upload PDF it answers (prompts/upload.md is the
contract). Errors stop it and write a fix request to paste back into the
same chat, as the narration's and the crop reply's do; warnings are what is
worth a second look but not wrong."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from remanga.json_io import json_from_reply

REPLY_NAME = "upload_reply.txt"
FIX_REQUEST_NAME = "upload_fix_request.md"

TITLE_MAX = 92          # YouTube cuts at 100, and " (01-48)" is added
TITLE_MIN = 20
LABEL_MAX = 28          # characters: three or four words is what reads at thumbnail size
HOOK_MAX = 1500         # characters of hook, all paragraphs
FRAMINGS = ("close", "medium", "wide")
COLORS = {"yellow": "#FFE600", "red": "#FF3B30", "white": "#FFFFFF", "light-blue": "#8FE3FF", "cyan": "#8FE3FF",
          "blue": "#8FE3FF", "pink": "#FF5FA8", "orange": "#FF9500", "green": "#5CFF8A", "purple": "#C08CFF"}
TINTS = {"blue": ["#06172e", "#d8ecff"], "navy": ["#06172e", "#d8ecff"], "red": ["#2a0505", "#ffd9cc"],
         "pink": ["#2e0616", "#ffe0ec"], "cyan": ["#002b33", "#d9fbff"], "purple": ["#1b0630", "#efe0ff"],
         "green": ["#03210f", "#dcffe9"], "gold": ["#2b1d00", "#fff1c4"], "sepia": ["#2b1a0e", "#f6e7d2"]}
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
# Words a title and a label may share without repeating the hook.
_COMMON = {"the", "a", "an", "of", "to", "in", "is", "and", "his", "her", "he", "she", "i", "me", "my", "it", "for",
           "on", "manga", "recap", "with", "who", "but", "so", "as", "at", "by", "be", "was", "are", "you", "only",
           "just", "too", "all", "not", "him", "them", "they", "this", "that"}

Box = tuple[int, int, int, int]


class UploadReplyError(ValueError):
    """A reply that was not used - nothing changed. `fix_request` is the file
    to paste back to the LLM, when it is the LLM's to fix."""

    def __init__(self, message: str, errors: list[str], fix_request: Path | None = None):
        super().__init__(message)
        self.errors = errors
        self.fix_request = fix_request


@dataclass
class Tile:
    image: str
    subject: Box
    framing: str = "medium"
    tint: list[str] | None = None
    avoid: list[Box] = field(default_factory=list)
    share: float | None = None


@dataclass
class Label:
    text: str
    tile: int
    color: str = COLORS["yellow"]
    arrow: bool = False


@dataclass
class Variant:
    letter: str
    angle: str
    title: str
    tiles: list[Tile]
    labels: list[Label]
    badge: bool = True


@dataclass
class UploadPlan:
    upload_id: str | None = None
    variants: list[Variant] = field(default_factory=list)
    hook: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _box(value: Any, where: str, plan: UploadPlan) -> Box | None:
    if (not isinstance(value, list) or len(value) != 4
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        plan.errors.append(f"{where}: {json.dumps(value)[:50]} is not a box - [ymin, xmin, ymax, xmax] in "
                           f"thousandths of the image")
        return None
    box = tuple(round(v) for v in value)
    if not all(0 <= v <= 1000 for v in box) or not (box[0] < box[2] and box[1] < box[3]):
        plan.errors.append(f"{where}: {list(box)} - every number is 0-1000, ymin under ymax, xmin under xmax")
        return None
    if min(box[2] - box[0], box[3] - box[1]) < 20:
        plan.errors.append(f"{where}: {list(box)} is too small to frame - box the whole face (or subject)")
        return None
    return box


def _color(value: Any, where: str, plan: UploadPlan) -> str:
    if value in (None, ""):
        return COLORS["yellow"]
    if isinstance(value, str) and _HEX.fullmatch(value.strip()):
        return value.strip()
    if isinstance(value, str) and value.strip().lower() in COLORS:
        return COLORS[value.strip().lower()]
    plan.errors.append(f"{where}: color {json.dumps(value)} - one of {', '.join(COLORS)} or a #RRGGBB hex")
    return COLORS["yellow"]


def _tint(value: Any, where: str, plan: UploadPlan) -> list[str] | None:
    if value in (None, "", "none"):
        return None
    if isinstance(value, str) and value.strip().lower() in TINTS:
        return TINTS[value.strip().lower()]
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) and _HEX.fullmatch(v) for v in value):
        return list(value)
    plan.errors.append(f"{where}: tint {json.dumps(value)} - one of {', '.join(TINTS)}, or [dark, light] hex colours")
    return None


def _tile(raw: Any, where: str, record: dict, plan: UploadPlan) -> Tile | None:
    if not isinstance(raw, dict):
        plan.errors.append(f'{where}: a tile is {{"image": ID, "subject": [ymin, xmin, ymax, xmax]}}')
        return None
    image = str(raw.get("image") or "").strip()
    if image not in record["candidates"]:
        plan.errors.append(f"{where}: image {json.dumps(image)} is not one of the images offered - use the id "
                           f"stamped at the foot of an image")
        return None
    subject = _box(raw.get("subject"), f"{where} subject", plan)
    framing = str(raw.get("framing") or "medium").strip().lower()
    if framing not in FRAMINGS:
        plan.errors.append(f"{where}: framing {json.dumps(framing)} - one of {', '.join(FRAMINGS)}")
    avoid = [b for b in (_box(a, f"{where} avoid", plan) for a in raw.get("avoid") or []) if b]
    share = raw.get("share")
    if share is not None and not (isinstance(share, (int, float)) and 0.25 <= share <= 0.75):
        plan.errors.append(f"{where}: share {json.dumps(share)} - the tile's part of the width, 0.25-0.75")
        share = None
    if subject is None:
        return None
    return Tile(image, subject, framing, _tint(raw.get("tint"), where, plan), avoid, share)


def _variant(raw: Any, n: int, record: dict, plan: UploadPlan) -> Variant | None:
    where = f"set {n}"
    if not isinstance(raw, dict):
        plan.errors.append(f"{where}: a set is an object with letter, angle, title and thumbnail")
        return None
    letter = str(raw.get("letter") or "ABC"[min(n, 3) - 1]).strip().upper()
    where = f"set {letter}"
    title = " ".join(str(raw.get("title") or "").split())
    if not TITLE_MIN <= len(title) <= TITLE_MAX:
        plan.errors.append(f"{where}: the title is {len(title)} characters - {TITLE_MIN} to {TITLE_MAX} (YouTube cuts "
                           f"at 100, and the chapters are added after it)")
    if "{" in title.replace("{num}", "") or "}" in title.replace("{num}", ""):
        plan.errors.append(f"{where}: the title has braces - write it plainly")
    thumb = raw.get("thumbnail")
    if not isinstance(thumb, dict):
        plan.errors.append(f'{where}: no "thumbnail" - {{"tiles": [...], "labels": [...]}}')
        return None
    raw_tiles = thumb.get("tiles") if isinstance(thumb.get("tiles"), list) else []
    if not 1 <= len(raw_tiles) <= 3:
        plan.errors.append(f"{where}: {len(raw_tiles)} tiles - a thumbnail has one, two or three")
    tiles = [_tile(t, f"{where} tile {i}", record, plan) for i, t in enumerate(raw_tiles, 1)]
    labels = []
    raw_labels = thumb.get("labels") if isinstance(thumb.get("labels"), list) else []
    if len(raw_labels) > 3:
        plan.errors.append(f"{where}: {len(raw_labels)} labels - at most three short ones")
    for i, lab in enumerate(raw_labels[:3], 1):
        at = f"{where} label {i}"
        text = " ".join(str((lab or {}).get("text") or "").replace("{", "").replace("}", "").split()).upper()
        tile = (lab or {}).get("tile", 1)
        if not text or len(text) > LABEL_MAX:
            plan.errors.append(f"{at}: {json.dumps(text)} - 1 to {LABEL_MAX} characters, three or four words")
            continue
        if not isinstance(tile, int) or not 1 <= tile <= max(1, len(raw_tiles)):
            plan.errors.append(f"{at}: tile {json.dumps(tile)} - the number of the tile it sits on (1 = left)")
            continue
        labels.append(Label(text, tile, _color(lab.get("color"), at, plan), bool(lab.get("arrow"))))
    if any(t is None for t in tiles):
        return None
    variant = Variant(letter, " ".join(str(raw.get("angle") or "").split()), title, tiles, labels,
                      raw.get("badge", True) is not False)
    shared = _words(title) & {w for lab in labels for w in _words(lab.text)}
    if shared:
        plan.warnings.append(f"{where}: the thumbnail repeats the title's word(s) {', '.join(sorted(shared))} - each "
                             f"should carry its own half of the hook")
    return variant


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _COMMON and len(w) > 2}


def read_upload_reply(raw: str, record: dict) -> UploadPlan:
    """The reply read and checked against the PDF's record; nothing raised -
    the errors are collected for one fix request."""
    plan = UploadPlan()
    try:
        doc = json_from_reply(raw)
    except json.JSONDecodeError as error:
        plan.errors.append(f"the reply is not valid JSON ({error.msg} at line {error.lineno}, column {error.colno}) "
                           f"- one JSON object, double quotes, no trailing commas")
        return plan
    if not isinstance(doc, dict):
        plan.errors.append('the reply is not a JSON object with "upload", "sets" and "description"')
        return plan
    plan.upload_id = str(doc["upload"]).strip().lower() if doc.get("upload") else None
    sets = doc.get("sets") if isinstance(doc.get("sets"), list) else []
    if not 1 <= len(sets) <= 3:
        plan.errors.append(f'"sets" has {len(sets)} entries - one to three (A, B, C)')
    for n, raw_set in enumerate(sets[:3], 1):
        variant = _variant(raw_set, n, record, plan)
        if variant:
            plan.variants.append(variant)
    letters = [v.letter for v in plan.variants]
    if len(set(letters)) != len(letters) or not set(letters) <= set("ABC"):
        plan.errors.append(f"the sets' letters are {', '.join(letters)} - A, B and C, once each")
    titles = [v.title.lower() for v in plan.variants]
    if len(set(titles)) != len(titles):
        plan.warnings.append("two sets have the same title - each set should be a different angle")
    desc = doc.get("description") if isinstance(doc.get("description"), dict) else {}
    hook = desc.get("hook")
    if isinstance(hook, str):
        hook = re.split(r"\n\s*\n", hook)
    plan.hook = [" ".join(str(p).split()) for p in hook or [] if str(p).strip()] if isinstance(hook, list) else []
    if not 1 <= len(plan.hook) <= 3:
        plan.errors.append(f"the description's hook has {len(plan.hook)} paragraph(s) - one to three (two is usual)")
    elif sum(len(p) for p in plan.hook) > HOOK_MAX:
        plan.errors.append(f"the description's hook is {sum(len(p) for p in plan.hook)} characters - keep it under "
                           f"{HOOK_MAX}")
    tags = desc.get("hashtags") if isinstance(desc.get("hashtags"), list) else []
    plan.hashtags = ["#" + re.sub(r"[^\w]", "", str(t).lstrip("#")) for t in tags if re.sub(r"[^\w]", "", str(t))]
    if not 3 <= len(plan.hashtags) <= 10:
        plan.errors.append(f"the description has {len(plan.hashtags)} hashtags - three to ten")
    problems = doc.get("problems") or []
    plan.problems = [str(p) for p in (problems if isinstance(problems, list) else [problems]) if str(p).strip()]
    return plan


def misplaced(plan: UploadPlan, record: dict) -> str | None:
    if plan.upload_id is not None and plan.upload_id != record["id"]:
        return (f"This reply answers another upload PDF (upload {plan.upload_id}); the one made last is upload "
                f"{record['id']}. Send that one to the LLM, or - if this reply does answer it - change its "
                f'"upload" to "{record["id"]}".')
    return None


def fix_request_text(errors: list[str]) -> str:
    return "\n".join([
        "# Fix request: the upload reply", "",
        "remanga could not use your reply - these need fixing:", "",
        *[f"- {error}" for error in errors], "",
        "Fix only these, checked against the images, and reply with the whole JSON again - every set and the "
        "description - as one ```json block, nothing before or after it.", ""])
