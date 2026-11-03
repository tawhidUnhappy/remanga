"""Figures and speech bubbles that cross a panel box - the cases a panel
detector gets wrong most, and the ones a crop has to decide: a caption cut in
half by two boxes, a character drawn across several frames, a head breaking
out of its frame, a bubble out in the gutter. Found by comparing what the
detector saw on the page (found.py) with the boxes the crop PDF draws. Each
becomes a hint: a dashed box with a label - F1 a figure, B1 a bubble - that
a reply can use like a numbered box, and a suggested fix in the plan's own
words.

How a hint is decided - the way a guided-view editor frames a page: never
cut into a neighbouring panel when it can be helped, a balloon goes with the
art it belongs to, a figure is never cut where it can be shown whole:

- a bubble belongs to the panel its tail points into (else the one clearly
  holding most of it, else the one it sits nearer the middle of), and that
  panel is widened over it: `2+B1`, the page exact;
- a figure mostly in one frame (70%+) widens that frame over it: `1+F1`;
- a figure across frames of one tier or one column, whose rectangle takes
  in no other frame, joins them into one shot: `1+2`;
- any other figure across frames is a shot of its own beside the frames:
  `F1`, the page exact - they overlap on purpose;
- a figure or bubble no box covers is a panel the detector missed: it joins
  the box beside it when that takes in nothing else, else it stands alone.

Only a suggestion: the LLM (prompts/crop.md) or Claude decides."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from remanga.crop_plan.grammar import Box

# Smallest figure / bubble worth a hint, as a share of the page's area.
MIN_FIGURE_AREA = 0.02
MIN_BUBBLE_AREA = 0.002
# This much of it inside one box: it is in that frame (anything else it
# touches is an inset drawn over the frame).
INSIDE = 0.9
# A share of a figure (bubble) this big in a box is a part worth keeping whole.
FIGURE_PART, BUBBLE_PART = 0.15, 0.2
# A figure this much in one frame widens that frame rather than joining.
MOSTLY = 0.7
# A suggested rectangle may take in at most this much of another box.
SWALLOW = 0.25
# A bubble with no tail goes with the box holding most of it only when that
# box holds this much more than the next.
CLEAR_LEAD = 0.15
# A box this close (thousandths) to stray art is the panel it belongs to.
NEAR = 40
MAX_HINTS = 6
_STEPS = 12   # sample points a side
# A box this thin (thousandths) is a strip worth a note; two boxes overlapping
# this much (intersection over union) are one panel boxed twice.
THIN = 110
DUPLICATE = 0.8


@dataclass(frozen=True)
class Hint:
    label: str                  # F1, B1 - what the reply calls it
    kind: str                   # figure | bubble
    box_1000: Box               # [ymin, xmin, ymax, xmax] in thousandths of the page
    why: str                    # what is wrong, in words
    touches: tuple[int, ...]    # the boxes it overlaps, by number
    suggest: str                # a panel in the plan's grammar ("" - only worth a look)
    exact: bool                 # the suggestion needs the page exact

    def record(self) -> dict:
        return {**asdict(self), "box_1000": list(self.box_1000), "touches": list(self.touches)}


def _area(box: Box) -> float:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _inside_share(box: Box, outer: Box) -> float:
    height = min(box[2], outer[2]) - max(box[0], outer[0])
    width = min(box[3], outer[3]) - max(box[1], outer[1])
    area = _area(box)
    return max(0, height) * max(0, width) / area if area else 0.0


def _union(*boxes: Box) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _gap(a: Box, b: Box) -> float:
    dy = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dx = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return max(dy, dx)


def _shares(item: Box, boxes: Sequence[Box]) -> tuple[list[float], float]:
    """How much of `item` lies in each box, and how much in none - sampled on
    a grid, so overlapping boxes are counted right."""
    inside = [0] * len(boxes)
    outside = 0
    for i in range(_STEPS):
        y = item[0] + (i + 0.5) * (item[2] - item[0]) / _STEPS
        for j in range(_STEPS):
            x = item[1] + (j + 0.5) * (item[3] - item[1]) / _STEPS
            hit = False
            for k, b in enumerate(boxes):
                if b[0] <= y <= b[2] and b[1] <= x <= b[3]:
                    inside[k] += 1
                    hit = True
            outside += not hit
    total = _STEPS * _STEPS
    return [n / total for n in inside], outside / total


def _swallows(rect: Box, boxes: Sequence[Box], keep: set[int]) -> bool:
    return any(_inside_share(b, rect) >= SWALLOW for k, b in enumerate(boxes) if k not in keep)


def _one_line(boxes: Sequence[Box]) -> bool:
    """Every box in one tier (they share most of their height) or one column."""
    def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
        return max(0, min(a1, b1) - max(a0, b0)) / max(1e-9, min(a1 - a0, b1 - b0))

    pairs = [(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:]]
    return (all(overlap(a[0], a[2], b[0], b[2]) >= 0.5 for a, b in pairs)
            or all(overlap(a[1], a[3], b[1], b[3]) >= 0.5 for a, b in pairs))


def _to_1000(box: Sequence[float], size: Sequence[int]) -> Box:
    w, h = size
    x1, y1, x2, y2 = box
    clamp = lambda v: max(0, min(1000, round(v)))  # noqa: E731
    return (clamp(y1 * 1000 / h), clamp(x1 * 1000 / w), clamp(y2 * 1000 / h), clamp(x2 * 1000 / w))


def _nums(indexes: Sequence[int]) -> str:
    names = [str(i + 1) for i in indexes]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _figure(box: Box, boxes: Sequence[Box]) -> tuple[str, tuple[int, ...], str, bool] | None:
    shares, outside = _shares(box, boxes)
    main = max(range(len(boxes)), key=shares.__getitem__) if boxes else -1
    best = shares[main] if boxes else 0.0
    if best >= INSIDE:
        return None
    parts = [k for k, s in enumerate(shares) if s >= FIGURE_PART]
    if len(parts) >= 2:
        why = f"a figure across boxes {_nums(parts)}"
        if best >= MOSTLY:
            return why, tuple(parts), f"{main + 1}+{{label}}", True
        frames = [boxes[k] for k in parts]
        if _one_line(frames) and not _swallows(_union(*frames, box), boxes, set(parts)):
            return why, tuple(parts), "+".join(str(k + 1) for k in parts), False
        return why, tuple(parts), "{label}", True
    if outside >= 0.3 and best >= 0.3:
        widened = _union(boxes[main], box)
        why = f"a figure breaking out of box {main + 1}"
        if _swallows(widened, boxes, {main}):
            return why, (main,), "", False
        return why, (main,), f"{main + 1}+{{label}}", True
    if outside >= 0.6:
        near = min(range(len(boxes)), key=lambda k: _gap(box, boxes[k])) if boxes else -1
        if near >= 0 and _gap(box, boxes[near]) <= NEAR and not _swallows(_union(boxes[near], box), boxes, {near}):
            return f"a figure no box covers, beside box {near + 1}", (near,), f"{near + 1}+{{label}}", True
        return "a figure no box covers", (), "{label}", False
    return None


def _bubble(box: Box, boxes: Sequence[Box], tails: Sequence[Box]) -> tuple[str, tuple[int, ...], str, bool] | None:
    shares, outside = _shares(box, boxes)
    if not boxes or max(shares) >= INSIDE:
        return None
    owner = -1
    for tail in tails:   # the tail points into the panel the words belong to
        cy, cx = (tail[0] + tail[2]) / 2, (tail[1] + tail[3]) / 2
        owner = next((k for k, b in enumerate(boxes) if b[0] <= cy <= b[2] and b[1] <= cx <= b[3]), owner)
    if owner < 0:
        ranked = sorted(range(len(boxes)), key=shares.__getitem__, reverse=True)
        owner = ranked[0]
        if shares[owner] == 0:
            owner = min(range(len(boxes)), key=lambda k: _gap(box, boxes[k]))
        elif len(ranked) > 1 and shares[owner] - shares[ranked[1]] < CLEAR_LEAD:
            # Inside two boxes about as much (they overlap, or it sits on the
            # border): a caption with no tail goes with the panel it sits nearer the middle of.
            cy, cx = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            owner = min(ranked[:2], key=lambda k: ((boxes[k][0] + boxes[k][2]) / 2 - cy) ** 2
                        + ((boxes[k][1] + boxes[k][3]) / 2 - cx) ** 2)
    parts = [k for k, s in enumerate(shares) if s >= BUBBLE_PART]
    widen = f"{owner + 1}+{{label}}"
    if len(parts) >= 2:
        why = f"a bubble split between boxes {_nums(parts)} - box {owner + 1} holds its moment"
        return why, tuple(parts), widen, True
    if outside >= 0.25 and max(shares) >= 0.25:
        return f"a bubble hanging out of box {owner + 1}", (owner,), widen, True
    if outside >= 0.6:
        if _gap(box, boxes[owner]) <= NEAR * 1.5:
            return f"a bubble no box covers, beside box {owner + 1}", (owner,), widen, True
        return "a bubble no box covers", (), "", False
    return None


def find_hints(boxes: Sequence[Box], found: dict | None) -> list[Hint]:
    """The page's hints, worst first: figures across frames, then bubbles,
    then stray art - at most MAX_HINTS."""
    if not found or not found.get("size"):
        return []
    size = found["size"]
    figures = [b for b in (_to_1000(f, size) for f in found.get("figures") or []) if _area(b) >= MIN_FIGURE_AREA * 1e6]
    texts = found.get("texts") or []
    if texts and len(found.get("balloons") or []) == len(texts):
        texts = found["balloons"]   # the whole balloon, not just its lettering (found.py)
    essential = found.get("essential") or [True] * len(texts)
    tails_of: dict[int, list[Box]] = {}
    for text, tail in found.get("text_tails") or []:
        if 0 <= tail < len(found.get("tails") or []):
            tails_of.setdefault(text, []).append(_to_1000(found["tails"][tail], size))
    raw: list[tuple[int, str, Box, tuple]] = []
    for box in figures:
        decided = _figure(box, boxes)
        if decided:
            raw.append((0 if len(decided[1]) >= 2 else 2, "figure", box, decided))
    for k, text in enumerate(texts):
        box = _to_1000(text, size)
        if (k < len(essential) and not essential[k]) or _area(box) < MIN_BUBBLE_AREA * 1e6:
            continue
        decided = _bubble(box, boxes, tails_of.get(k, []))
        if decided:
            raw.append((1 if len(decided[1]) >= 2 else 3, "bubble", box, decided))
    raw.sort(key=lambda r: r[0])
    kept = sorted(raw[:MAX_HINTS], key=lambda r: (r[1], r[2][0], r[2][1]))
    hints, count = [], {"figure": 0, "bubble": 0}
    for _, kind, box, (why, touches, suggest, exact) in kept:
        count[kind] += 1
        label = f"{kind[0].upper()}{count[kind]}"
        hints.append(Hint(label, kind, box, why, tuple(t + 1 for t in touches), suggest.format(label=label), exact))
    return hints


def still_cut(hint: dict, panels: Sequence[Box]) -> bool:
    """Whether a hint's figure or bubble is still cut by every panel the
    reply made: no panel holds (nearly) all of it."""
    box = tuple(hint["box_1000"])
    need = 0.9 if hint["kind"] == "bubble" else 0.85
    return not any(_inside_share(box, p) >= need for p in panels)


def _iou(a: Box, b: Box) -> float:
    height = min(a[2], b[2]) - max(a[0], b[0])
    width = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0, height) * max(0, width)
    union = _area(a) + _area(b) - inter
    return inter / union if union else 0.0


def _neighbour(i: int, boxes: Sequence[Box]) -> int | None:
    """The box a thin strip most likely belongs to: the nearest one beside
    it along its long side."""
    strip = boxes[i]
    across = 1 if strip[2] - strip[0] < strip[3] - strip[1] else 0   # a flat strip shares x with its neighbour

    def shared(b: Box) -> float:
        a0, a1, b0, b1 = (strip[1], strip[3], b[1], b[3]) if across else (strip[0], strip[2], b[0], b[2])
        return max(0, min(a1, b1) - max(a0, b0)) / max(1, a1 - a0)

    near = [k for k, b in enumerate(boxes) if k != i and _gap(strip, b) <= NEAR and shared(b) >= 0.5]
    return min(near, key=lambda k: (_gap(strip, boxes[k]), -_area(boxes[k]))) if near else None


def find_notes(boxes: Sequence[Box], found: dict | None) -> list[str]:
    """Boxes worth a look on their own: a thin strip (a sliver between panels,
    or a caption cut off its panel - what is in it tells which), two boxes over
    one panel, and a box inside another (an inset - or one box around several
    panels)."""
    notes = []
    size = (found or {}).get("size")
    figures = [_to_1000(f, size) for f in (found or {}).get("figures") or []] if size else []
    texts = (found or {}).get("balloons") or (found or {}).get("texts") or []
    words = [_to_1000(t, size) for t in texts] if size else []
    for i, b in enumerate(boxes):
        height, width = b[2] - b[0], b[3] - b[1]
        if min(height, width) >= THIN:
            continue
        what = f"box {i + 1} is a thin strip ({width}x{height} thousandths)"
        near = _neighbour(i, boxes)
        join = f" - {i + 1}+{near + 1}?" if near is not None else ""
        if not size:
            notes.append(f"{what}: a sliver between panels (leave it out), or part of the panel beside it{join}")
        elif any(b[0] <= (t[0] + t[2]) / 2 <= b[2] and b[1] <= (t[1] + t[3]) / 2 <= b[3] for t in words):
            notes.append(f"{what} holding words: a caption cut off its panel? join it to the panel it belongs to"
                         f"{join}")
        elif sum(_shares(b, [f])[0][0] for f in figures) < 0.15:
            notes.append(f"{what} with no figure or words in it: a sliver between panels - leave {i + 1} out")
        else:
            notes.append(f"{what} with part of a figure in it: part of the panel beside it{join}")
    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            small, big = (i, j) if _area(a) <= _area(b) else (j, i)
            inside = _inside_share(boxes[small], boxes[big])
            if _iou(a, b) >= DUPLICATE:
                notes.append(f"boxes {i + 1} and {j + 1} are nearly the same box - one panel boxed twice: keep one")
            elif inside >= 0.9:
                notes.append(f"box {small + 1} lies inside box {big + 1}: an inset drawn over it (fine), or box "
                             f"{big + 1} holds two or more panels - then a box for each")
    # Boxes that merely overlap say nothing: a slanted border overlaps its
    # neighbour's box as much as one panel cut in two does (20 of 36 pages of
    # a chapter drawn with slanted borders), and a note on every one is noise.
    return notes
