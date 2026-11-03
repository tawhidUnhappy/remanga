"""A crop plan's page lines applied to a printed manga's marks (crops.json):
each page a line names gets exactly the panels it lists, in that order, and
every other page keeps what it has.

The numbers in a line are the boxes as they were drawn when the plan was
written - `base`: the crop PDF's record of them for an LLM's reply, crops.json
itself for Claude, who applies a plan straight after looking. The pages are
written over `current` (crops.json now), so a page no line names is never
touched."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from remanga.crop_plan.grammar import Box, PageLine
from remanga.json_io import has_real_json_content, read_json
from remanga.narration import page_files
from remanga.paths import get_crops_path

# A side shorter than this (thousandths of the page) is no panel: four box
# numbers read as one box (`1, 2, 3, 4`), or a slip. Under WARN_SIDE it is worth
# a look - a panel come back as a thin strip is the LLM's usual measuring slip.
MIN_SIDE = 10
WARN_SIDE = 30
# A joined or measured panel that takes in this much of another panel shows
# that panel's art twice.
SWALLOW_SHARE = 0.5


def page_record(project: str, chapter: str) -> dict:
    """crops.json, or - for a chapter with none yet - its pages with no marks."""
    path = get_crops_path(project, chapter)
    if has_real_json_content(path):
        return read_json(path)
    return {"chapter": str(chapter), "marks_format": 2,
            "pages": [{"page_index": i, "page_filename": p.name, "is_story_page": False, "panels": [],
                       "user_decided": False} for i, p in enumerate(page_files(project, chapter), start=1)]}


def page_boxes(page: dict) -> list[Box]:
    """A crops.json page's marks as [ymin, xmin, ymax, xmax] thousandths, in
    their order (the reading order: the cutter keeps list order)."""
    return [tuple(round(v) for v in panel["box_1000"]) for panel in page.get("panels") or []
            if panel.get("box_1000")]


@dataclass
class PagesOutcome:
    record: dict
    changed: list[str] = field(default_factory=list)   # a line per page the plan changed, in words
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def apply_page_lines(base: dict, current: dict, lines: list[PageLine], *, src: str = "manual",
                     every_page: bool = False) -> PagesOutcome:
    """`current` with every page in `lines` replaced by the panels its line
    lists, resolved against `base`'s boxes. Nothing is applied when anything
    is wrong (`errors`). `every_page` is an LLM reply's rule - it was handed a
    line for every page - so a page with no line is reported (it keeps its
    marks). `src` marks the panels the plan made; a box kept as it is keeps
    its own."""
    record = copy.deepcopy(current)
    outcome = PagesOutcome(record)
    base_pages = {p["page_index"]: p for p in base.get("pages", [])}
    pages = {p["page_index"]: p for p in record.get("pages", [])}
    seen: dict[int, int] = {}
    for line in lines:
        where = line.at()
        if line.page not in base_pages or line.page not in pages:
            outcome.errors.append(f"{where}: the chapter has no page {line.page} - its pages are "
                                  f"{min(pages, default=0)}-{max(pages, default=0)}")
            continue
        if line.page in seen:
            outcome.errors.append(f"{where}: page {line.page} is in the plan twice - one entry a page")
            continue
        seen[line.page] = line.line
        boxes = page_boxes(base_pages[line.page])
        panels = _resolve(line, boxes, base_pages[line.page], src, outcome)
        if panels is None:
            continue
        page = pages[line.page]
        before = page_boxes(page)
        page["panels"] = [{"panel_id": i, **panel} for i, panel in enumerate(panels, start=1)]
        page["is_story_page"] = bool(panels)
        page["user_decided"] = True
        page["custom_order"] = True
        if line.exact:
            page["exact"] = True
        else:
            page.pop("exact", None)
        after = page_boxes(page)
        if before not in (boxes, after):
            outcome.warnings.append(f"page {line.page} was changed after the boxes this plan numbers were "
                                    f"drawn - the plan's line replaced that change")
        note = _describe(line, len(boxes), bool(base_pages[line.page].get("exact")))
        if note:
            outcome.changed.append(f"page {line.page}: {note}")
    if every_page:
        missing = sorted(set(pages) - set(seen))
        if missing:
            outcome.warnings.append(f"page(s) {_spans(missing)} are not in the reply - kept as they are")
    return outcome


def _resolve(line: PageLine, boxes: list[Box], page: dict, src: str, outcome: PagesOutcome) -> list[dict] | None:
    """The line's panels as crops.json panels, or None (errors noted). A hint
    label (F1, B1) stands for its box on the page, as drawn in the crop PDF."""
    where = line.at()
    hints = {h["label"]: tuple(h["box_1000"]) for h in page.get("hints") or []}
    used: set[int] = set()
    out, rects, made = [], [], []
    ok = True
    for panel in line.panels:
        for label in panel.hints:
            if label not in hints:
                have = f"its hints are {', '.join(hints)}" if hints else "it has no hints"
                outcome.errors.append(f"{where}: page {line.page} has no {label} - {have}")
                ok = False
        for mark in panel.marks:
            if not 1 <= mark <= len(boxes):
                have = f"boxes 1-{len(boxes)}" if boxes else "no boxes"
                outcome.errors.append(f"{where}: page {line.page} has {have} - there is no box {mark}")
                ok = False
            elif mark in used:
                outcome.errors.append(f"{where}: box {mark} is in two panels - each box goes in one panel")
                ok = False
            used.add(mark)
        for box in panel.boxes:
            problem = _box_problem(box)
            if problem:
                outcome.errors.append(f"{where}: {','.join(map(str, box))} {problem}")
                ok = False
        if not ok:
            continue
        parts = [boxes[m - 1] for m in panel.marks] + [hints[h] for h in panel.hints] + list(panel.boxes)
        rect = (min(p[0] for p in parts), min(p[1] for p in parts), max(p[2] for p in parts), max(p[3] for p in parts))
        kept = not panel.boxes and not panel.hints and len(panel.marks) == 1
        own = (page["panels"][panel.marks[0] - 1].get("src") if kept else None) or src
        out.append({"box_1000": list(rect), "src": own})
        rects.append(rect)
        made.append(not kept)
        height, width = rect[2] - rect[0], rect[3] - rect[1]
        if not kept and min(height, width) < WARN_SIDE:
            outcome.warnings.append(f"page {line.page}: panel {panel.text} is only {width}x{height} "
                                    f"thousandths - a thin strip; look at it")
    if not ok:
        return None
    for i, rect in enumerate(rects):
        for j, other in enumerate(rects):
            if i != j and made[i] and _inside_share(other, rect) >= SWALLOW_SHARE:
                outcome.warnings.append(f"page {line.page}: panel {line.panels[i].text} takes in most of panel "
                                        f"{line.panels[j].text} - its art shows in both")
    return out


def _box_problem(box: Box) -> str | None:
    y0, x0, y1, x1 = box
    if not all(0 <= v <= 1000 for v in box):
        return "is outside the page - every number is 0-1000"
    if not (y0 < y1 and x0 < x1):
        return "is not ymin,xmin,ymax,xmax - ymin must be under ymax and xmin under xmax"
    if min(y1 - y0, x1 - x0) < MIN_SIDE:
        return f"is {x1 - x0}x{y1 - y0} thousandths - too small to be a panel (box numbers are separated by /)"
    return None


def _inside_share(box: Box, outer: Box) -> float:
    """How much of `box` lies inside `outer`."""
    height = min(box[2], outer[2]) - max(box[0], outer[0])
    width = min(box[3], outer[3]) - max(box[1], outer[1])
    area = (box[2] - box[0]) * (box[3] - box[1])
    return max(0, height) * max(0, width) / area if area else 0.0


def _describe(line: PageLine, boxes: int, was_exact: bool) -> str:
    """What a line changes from the boxes as they were, in a few words - empty
    when it keeps them all, in order, as exact as they were."""
    marks = [m for p in line.panels for m in p.marks]
    same = marks == list(range(1, boxes + 1)) and all(len(p.marks) == 1 and not p.boxes and not p.hints
                                                       for p in line.panels)
    if same and line.exact == was_exact:
        return ""
    if not line.panels:
        return "no panels" + (f" (had {boxes})" if boxes else "")
    notes = []
    dropped = [m for m in range(1, boxes + 1) if m not in marks]
    if dropped:
        notes.append(f"box{'es' if len(dropped) > 1 else ''} {', '.join(map(str, dropped))} dropped")
    joined = [p.text for p in line.panels if len(p.marks) > 1 and not p.boxes and not p.hints]
    if joined:
        notes.append(f"{', '.join(joined)} joined")
    widened = [p.text for p in line.panels if p.marks and (p.boxes or p.hints)]
    if widened:
        notes.append(f"{', '.join(widened)} widened")
    shots = [p.text for p in line.panels if p.hints and not p.marks and not p.boxes]
    if shots:
        notes.append(f"{', '.join(shots)} as a panel of {'their' if len(shots) > 1 else 'its'} own")
    measured = sum(1 for p in line.panels if p.boxes and not p.marks)
    if measured:
        notes.append(f"{measured} measured box{'es' if measured > 1 else ''}")
    firsts = [min(p.marks) for p in line.panels if p.marks]
    if firsts != sorted(firsts):
        notes.append("order changed")
    if line.exact != was_exact:
        notes.append("exact" if line.exact else "no longer exact")
    return ", ".join(notes) + "  ->  " + " / ".join(p.text for p in line.panels)


def _spans(numbers: list[int]) -> str:
    """1, 2, 3, 5 -> 1-3, 5"""
    spans: list[list[int]] = []
    for n in numbers:
        if spans and n == spans[-1][1] + 1:
            spans[-1][1] = n
        else:
            spans.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in spans)
