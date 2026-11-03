"""The crop PDF's text page and its record (prompts/crop.md is the contract).

The text page tells the LLM the chapter, the reading direction, the boxes as
they are drawn and the hints (breakouts.py: figures and bubbles that cross a
box), and ends with the reply skeleton - JSON with an entry for every page,
its boxes as they are - which it copies and corrects.

The record (pdf/chapter_N/crop_marks.json) is those boxes exactly as drawn,
with a short id the skeleton's first line carries: the reply's numbers mean
the boxes in the PDF, so the reply is read against this record and never
against crops.json as it is later - after a reply is used, crops.json is
renumbered, and reading the same reply against it would swap panels back. A
reply whose id is not the record's was written for another crop PDF."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remanga.crop_plan.breakouts import find_hints, find_notes
from remanga.crop_plan.strip import StripNow, cuts_of
from remanga.json_io import read_json_or, write_json

RECORD_NAME = "crop_marks.json"


def _with_id(record: dict, body) -> dict:
    record["id"] = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:6]
    return record


def page_record_of(chapter: str, crops: dict, found: dict[str, dict] | None = None) -> dict:
    """What a page manga's crop PDF draws: every page's boxes, in order, and
    the hints (breakouts.py) found from what the detector saw on it."""
    pages = []
    for p in crops.get("pages", []):
        panels = [{"box_1000": [round(v) for v in q["box_1000"]], "src": q.get("src", "manual")}
                  for q in p.get("panels") or [] if q.get("box_1000")]
        boxes = [tuple(q["box_1000"]) for q in panels]
        seen = (found or {}).get(p["page_filename"])
        hints, notes = find_hints(boxes, seen), find_notes(boxes, seen)
        pages.append({"page_index": p["page_index"], "page_filename": p["page_filename"], "panels": panels,
                      **({"exact": True} if p.get("exact") else {}),
                      **({"hints": [h.record() for h in hints]} if hints else {}),
                      **({"notes": notes} if notes else {})})
    body = [[p["page_index"], p["page_filename"], [q["box_1000"] for q in p["panels"]], bool(p.get("exact")),
             [h["box_1000"] for h in p.get("hints", [])], p.get("notes", [])] for p in pages]
    return _with_id({"layout": "pages", "chapter": str(chapter), "pages": pages}, body)


def strip_record_of(chapter: str, now: StripNow) -> dict:
    """What a long strip's crop PDF draws: its panels, and the images they are rows of."""
    from remanga.plugins.long_strip.marks import sources_record

    panels = [list(p) for p in now.panels]
    record = {"layout": "long_strip", "chapter": str(chapter), "panels": panels,
              "sources": sources_record(now.sources), "height": now.height}
    return _with_id(record, [panels, record["sources"]])


def write_record(pdf_dir: Path, record: dict) -> None:
    write_json(pdf_dir / RECORD_NAME, record)


def read_record(pdf_dir: Path) -> dict | None:
    return read_json_or(pdf_dir / RECORD_NAME, None)


def _identity_lines(identity: dict) -> list[str]:
    return [f"{key}: {value}" for key, value in identity.items()]


def page_text(identity: dict, record: dict, found_by: str, part_pages: list[int], index: int,
              total: int) -> list[str]:
    """The text page of part `index` of `total`: on the first, everything -
    the boxes as numbers, the hints and the reply skeleton; on the others,
    which pages the part holds."""
    pages = record["pages"]
    hinted = [p for p in pages if p.get("hints")]
    lines = [
        *_identity_lines(identity),
        'layout: pages - after this text, one manga page per PDF page, stamped "page N" at its foot',
        f"pages: {len(pages)} (page {pages[0]['page_index']} to page {pages[-1]['page_index']})"
        if pages else "pages: none",
        f"boxes: {sum(len(p['panels']) for p in pages)} on {sum(1 for p in pages if p['panels'])} pages, "
        f"{found_by}",
        f"hints: {sum(len(p['hints']) for p in hinted)} on {len(hinted)} pages - figures (F) and bubbles (B) that "
        f"cross a box, dashed on the pages" if hinted else "hints: none",
    ]
    if total > 1:
        lines.append(f"part {index} of {total}: page {part_pages[0]} to page {part_pages[-1]}"
                     + (" - the reply skeleton is on part 1" if index > 1 else ""))
    if index > 1:
        return lines
    lines += ["", "The boxes as drawn - page: number:[ymin,xmin,ymax,xmax] in thousandths of the page:"]
    for page in pages:
        # No space inside an entry, so the page's wrap never parts a number from its box.
        boxes = "  ".join(f"{i}:[{','.join(map(str, q['box_1000']))}]" for i, q in enumerate(page["panels"], 1))
        lines.append(f"page {page['page_index']}{' (exact)' if page.get('exact') else ''}: {boxes or 'no boxes'}")
    if hinted:
        lines += ["", "Hints - a figure or bubble the program saw crossing a box (dashed and labelled on the page),",
                  "with what it would do. Use a label in a panel like a box number; leave a hint out to ignore it:"]
        for page in hinted:
            for hint in page["hints"]:
                box = ",".join(map(str, hint["box_1000"]))
                fix = (f"suggested: {hint['suggest']}" + (" (page exact)" if hint["exact"] else "")
                       if hint["suggest"] else "no suggestion - look at it")
                lines.append(f"page {page['page_index']}: {hint['label']}:[{box}] {hint['why']}; {fix}")
    noted = [p for p in pages if p.get("notes")]
    if noted:
        lines += ["", "Boxes worth a look - what the program noticed about the boxes themselves:"]
        lines += [f"page {page['page_index']}: {note}" for page in noted for note in page["notes"]]
    # No backticks here: the text page's standard font prints ` as a curly quote.
    lines += ["", "Reply skeleton - every page with its boxes as they are now. Copy all of it, correct the pages",
              'that are wrong (add a short "why" to each page you change), and reply with it as one JSON',
              "code block:",
              "{",
              f'  "chapter": {json.dumps(str(record["chapter"]))},',
              f'  "marks": "{record["id"]}",',
              '  "pages": [']
    for n, page in enumerate(pages, start=1):
        panels = ", ".join(str(i) for i in range(1, len(page["panels"]) + 1))
        exact = ', "exact": true' if page.get("exact") else ""
        lines.append(f'    {{"page": {page["page_index"]}{exact}, "panels": [{panels}]}}'
                     + ("," if n < len(pages) else ""))
    lines += ["  ],", '  "problems": []', "}"]
    return lines


def strip_text(identity: dict, record: dict, now: StripNow, found_by: str, index: int, total: int) -> list[str]:
    """A long strip's text page: the panels as rows, the cuts, the skeleton."""
    width = now.view.runs[0].width
    lines = [
        *_identity_lines(identity),
        "layout: long strip (webtoon) - after this text, the chapter as one tall strip cut into columns:",
        "  read each column top to bottom, the columns left to right. Rows count from 0 at the top of",
        "  the chapter; every row number is on the ruler at the left of each column.",
        f"strip: {record['height']} rows, {width} px wide - {len(record['panels'])} panels, {found_by}",
    ]
    if total > 1:
        lines.append(f"part {index} of {total}" + (" - the reply skeleton is on part 1" if index > 1 else ""))
    if index > 1:
        return lines
    lines += ["", "The panels as drawn - number:top-bottom rows:",
              "  ".join(f"{i}:{t}-{b}" for i, (t, b) in enumerate(record["panels"], 1)),
              "", "The cuts as drawn (the red labels): " + (", ".join(map(str, cuts_of(
                  [tuple(p) for p in record["panels"]]))) or "none"),
              "", "Reply skeleton - add your edits to the list, one an entry (leave it empty when every cut is",
              "right), and reply with it as one JSON code block:",
              "{",
              f'  "chapter": {json.dumps(str(record["chapter"]))},',
              f'  "marks": "{record["id"]}",',
              '  "edits": [],',
              '  "problems": []',
              "}"]
    return lines
