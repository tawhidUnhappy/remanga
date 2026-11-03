"""A crop plan as written: how a chapter's pages are cut into panels. An LLM
answers the crop PDF with one (prompts/crop.md); Claude writes one after
looking at the pages (.claude/skills/remanga-long-recap/crop.py). This
module only reads it - pages.py and strip.py apply it.

The plan is JSON:

    {"chapter": "2.1", "marks": "3f9c2a",              which chapter, and which crop PDF
     "pages": [{"page": 6, "panels": [1, "3+4", [512, 40, 780, 488]]},
               {"page": 5, "exact": true, "panels": ["F1", 2, "1+B1"], "why": "..."},
               {"page": 13, "panels": []}],              no panels: credits, ads, blank
     "problems": ["page 14 looks like it belongs after 17"]}

    {"chapter": "5", "marks": "8b1d77",                  a long strip: edits to its cuts
     "edits": [{"join": 81738}, {"split": 45210}, {"move": [30110, 30200]},
               {"drop": 98100}, {"add": [1000, 2400]}]}

A panel is a number (a box drawn on the page as it is now), a measured box
[ymin, xmin, ymax, xmax] in thousandths of the page, or a string joining
parts with +: box numbers, hint labels (F1 a figure, B1 a bubble - dashed on
the page, see breakouts.py) and measured boxes written ymin,xmin,ymax,xmax.
The panel is the rectangle around its parts.

The plain lines this format replaced are still read, for older replies and
plan files:

    chapter 2.1 marks 3f9c2a
    page 6: 1 / 3+4 / 512,40,780,488    page 5 exact: F1 / 2    page 13: none
    join 81738    move 81738 81900    add 1000 2400    # a comment; "# problem: ..." is passed on"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from remanga.json_io import json_from_reply

Box = tuple[int, int, int, int]

HEADER = re.compile(r"chapter\s*:?\s*(\S+?)(?:\s+marks\s+([0-9a-f]+))?", re.IGNORECASE)
PAGE = re.compile(r"page\s+(\d+)\s*(exact)?\s*:\s*(.*)", re.IGNORECASE)
BOX = re.compile(r"\[?\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]?")
HINT = re.compile(r"[FB]\d+", re.IGNORECASE)
NONE = re.compile(r"none\b.*", re.IGNORECASE)
# How many rows each long-strip edit takes.
EDITS = {"split": 1, "join": 1, "drop": 1, "move": 2, "add": 2}
# What a pasted line may start with that is not part of it: a list bullet, or
# the backtick a chat wraps code in.
_LEAD = re.compile(r"^(?:[-*•]\s+|`+)")


@dataclass(frozen=True)
class Panel:
    """One panel to cut: the numbered boxes, hints and measured boxes it joins."""
    marks: tuple[int, ...]
    boxes: tuple[Box, ...]
    hints: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return "+".join([str(m) for m in self.marks] + list(self.hints) + [",".join(map(str, b)) for b in self.boxes])


@dataclass(frozen=True)
class PageLine:
    line: int                 # where it stands in what was pasted, 1-based (a JSON reply: its entry)
    page: int
    exact: bool
    panels: tuple[Panel, ...]  # none: no panels
    where: str = ""            # how an error names it, when not by its line

    def at(self) -> str:
        return self.where or f"line {self.line} (page {self.page})"


@dataclass(frozen=True)
class StripEdit:
    line: int
    op: str
    rows: tuple[int, ...]
    where: str = ""

    @property
    def text(self) -> str:
        return " ".join([self.op, *map(str, self.rows)])

    def at(self) -> str:
        return self.where or f"line {self.line}"


@dataclass
class Plan:
    chapter: str | None = None
    marks_id: str | None = None
    pages: list[PageLine] = field(default_factory=list)
    edits: list[StripEdit] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def read_reply(raw: str) -> Plan:
    """A pasted reply or a plan file, JSON or the older plain lines. Errors are
    collected, not raised - a fix request lists them all at once."""
    text = raw.lstrip("﻿").strip()
    if not _is_json(text):
        return read_plan(plan_text(text))
    try:
        doc = json_from_reply(text)
    except json.JSONDecodeError as error:
        return Plan(errors=[f"the reply is not valid JSON ({error.msg} at line {error.lineno}, column "
                            f"{error.colno}) - one JSON object, double quotes, no trailing commas"])
    return read_json_plan(doc)


def _is_json(text: str) -> bool:
    fenced = re.search(r"```([^\n]*)\n\s*(.)", text)
    if fenced:
        return fenced.group(1).strip().lower() == "json" or fenced.group(2) == "{"
    return text.startswith("{")


def read_json_plan(doc: Any) -> Plan:
    plan = Plan()
    if not isinstance(doc, dict):
        plan.errors.append('the reply is not a JSON object with "chapter", "marks" and "pages" (or "edits")')
        return plan
    if doc.get("chapter") not in (None, ""):
        plan.chapter = str(doc["chapter"]).strip()
    if doc.get("marks") not in (None, ""):
        plan.marks_id = str(doc["marks"]).strip().lower()
    problems = doc.get("problems") or []
    plan.problems += [str(p) for p in (problems if isinstance(problems, list) else [problems]) if str(p).strip()]
    pages, edits = doc.get("pages"), doc.get("edits")
    if pages is None and edits is None:
        plan.errors.append('the reply has no "pages" (printed pages) or "edits" (a long strip)')
    if pages is not None:
        _json_pages(pages, plan)
    if edits is not None:
        _json_edits(edits, plan)
    return plan


def _json_pages(pages: Any, plan: Plan) -> None:
    if not isinstance(pages, list):
        plan.errors.append('"pages" must be a list - one {"page": N, "panels": [...]} a page')
        return
    for n, entry in enumerate(pages, start=1):
        page = entry.get("page") if isinstance(entry, dict) else None
        if not isinstance(page, int) or isinstance(page, bool):
            plan.errors.append(f'pages entry {n}: needs "page" (its number) and "panels" - got '
                               f"{json.dumps(entry)[:80]}")
            continue
        where = f"page {page}"
        raw = entry.get("panels")
        if not isinstance(raw, list):
            plan.errors.append(f'{where}: "panels" must be a list - [] for a page with no panels')
            continue
        panels = [_json_panel(item, where, plan) for item in raw]
        if all(p is not None for p in panels):
            plan.pages.append(PageLine(n, page, bool(entry.get("exact")), tuple(panels), where=where))


def _json_panel(item: Any, where: str, plan: Plan) -> Panel | None:
    if isinstance(item, bool):
        pass
    elif isinstance(item, int):
        return Panel((item,), ())
    elif isinstance(item, str):
        return _token(item.strip(), where, plan)
    elif isinstance(item, list) and len(item) == 4 and all(isinstance(v, (int, float)) for v in item):
        return Panel((), (tuple(round(v) for v in item),))
    elif isinstance(item, dict):   # {"join": [2, "B1"], "box": [y0, x0, y1, x1]} - read, though never asked for
        joined = "+".join(str(p) for p in item.get("join") or [])
        box = item.get("box")
        if isinstance(box, list) and len(box) == 4:
            joined += ("+" if joined else "") + ",".join(str(round(v)) for v in box)
        if joined:
            return _token(joined, where, plan)
    plan.errors.append(f"{where}: {json.dumps(item)[:60]} is not a panel - a panel is a box number (3), a "
                       f'measured box [ymin, xmin, ymax, xmax], or parts joined in a string ("2+3", "1+B1")')
    return None


def _json_edits(edits: Any, plan: Plan) -> None:
    if not isinstance(edits, list):
        plan.errors.append('"edits" must be a list of edits - {"join": ROW}, {"split": ROW}, ...')
        return
    for n, entry in enumerate(edits, start=1):
        where = f"edit {n}"
        if isinstance(entry, str):
            if _read_line(entry.strip(), n, plan, where) is not True:
                plan.errors.append(f"{where}: `{entry}` is not an edit")
            continue
        ops = [op for op in EDITS if isinstance(entry, dict) and op in entry]
        if len(ops) != 1:
            plan.errors.append(f"{where}: {json.dumps(entry)[:80]} - an edit is one of "
                               f"{', '.join(EDITS)} with its row(s)")
            continue
        op, value = ops[0], entry[ops[0]]
        if op == "move" and "to" in entry:
            value = [value, entry["to"]]
        rows = value if isinstance(value, list) else [value]
        if len(rows) != EDITS[op] or not all(isinstance(r, int) and not isinstance(r, bool) for r in rows):
            plan.errors.append(f"{where}: {op} takes {EDITS[op]} row number(s) - got {json.dumps(value)}")
            continue
        plan.edits.append(StripEdit(n, op, tuple(rows), where=where))


def plan_text(raw: str) -> str:
    """The plan inside a pasted reply in the older plain-lines format. The LLM
    was asked for one fenced block and nothing else, but a paste can bring the
    fence along, or a sentence before or after it: with a fence, only what is
    inside it."""
    text = raw.lstrip("﻿")
    fenced = re.search(r"```[^\n]*\n(.*?)\n[ \t]*```", text, re.DOTALL)
    return fenced.group(1) if fenced else text


def read_plan(text: str) -> Plan:
    """Every line of a plain-lines plan read, errors collected rather than
    raised."""
    plan = Plan()
    for number, raw in enumerate(text.splitlines(), start=1):
        body, _, comment = raw.partition("#")
        if comment.strip().lower().startswith("problem"):
            plan.problems.append(comment.strip())
        line = _LEAD.sub("", body.strip()).strip().rstrip("`").strip()
        if not line:
            continue
        if _read_line(line, number, plan) is False:
            plan.errors.append(f"line {number}: `{line}` is not a line of the plan - a page line is "
                               f"`page N: ...`, a strip edit is split/join/move/drop/add with its rows")
    return plan


def _read_line(line: str, number: int, plan: Plan, where: str = "") -> bool | None:
    header = HEADER.fullmatch(line)
    if header and not where:
        if plan.chapter is not None:
            plan.errors.append(f"line {number}: a second chapter line - the plan has one, at the top")
        plan.chapter, plan.marks_id = header.group(1), (header.group(2) or "").lower() or None
        return True
    page = PAGE.fullmatch(line)
    if page and not where:
        panels = _panels(page.group(3), number, plan)
        if panels is not None:
            plan.pages.append(PageLine(number, int(page.group(1)), bool(page.group(2)), panels))
        return True
    op, *args = line.split() or [""]
    if op.lower() in EDITS:
        rows = [a.replace(",", "").replace("_", "") for a in args]
        at = where or f"line {number}"
        if len(rows) != EDITS[op.lower()] or not all(r.isdigit() for r in rows):
            plan.errors.append(f"{at}: `{line}` - {op.lower()} takes {EDITS[op.lower()]} row number(s)")
        else:
            plan.edits.append(StripEdit(number, op.lower(), tuple(int(r) for r in rows), where=where))
        return True
    return False


def _panels(rest: str, number: int, plan: Plan) -> tuple[Panel, ...] | None:
    """A page line's panels, or None (with the errors noted) when one of them
    cannot be read."""
    rest = rest.strip()
    if NONE.fullmatch(rest):
        return ()
    panels = [_token(t.strip(), f"line {number}", plan) for t in rest.split("/") if t.strip()]
    if not panels:
        plan.errors.append(f"line {number}: no panels after the colon - write `none` for a page with none")
        return None
    return tuple(panels) if all(p is not None for p in panels) else None


def _token(token: str, where: str, plan: Plan) -> Panel | None:
    """One panel - parts joined by + - or None with the error noted."""
    marks, boxes, hints = [], [], []
    for part in (p.strip() for p in token.split("+")):
        box = BOX.fullmatch(part)
        if part.isdigit():
            marks.append(int(part))
        elif HINT.fullmatch(part):
            hints.append(part.upper())
        elif box:
            boxes.append(tuple(int(v) for v in box.groups()))
        else:
            plan.errors.append(f"{where}: `{part}` in `{token}` is neither a box number, a hint (F1, B1) nor a "
                               f"measured box ymin,xmin,ymax,xmax")
            return None
    if not (marks or boxes or hints):
        plan.errors.append(f"{where}: an empty panel `{token}`")
        return None
    return Panel(tuple(marks), tuple(boxes), tuple(hints))
