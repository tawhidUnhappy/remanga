"""The upload PDF's text page and its record (prompts/upload.md is the contract).

The text page gives the LLM the manga's facts, the story and the images it
may use, and ends with the reply skeleton. The record
(pdf/upload/upload_marks.json) is what the PDF offered - every image's id,
file and size - under a short id the skeleton carries, so a reply is read
against the images it was written for, and an older reply is caught."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remanga.json_io import read_json_or, write_json
from remanga.upload_plan.candidates import Candidate

RECORD_NAME = "upload_marks.json"
LETTERS = "ABC"


def record_of(project: str, chapters: list[str], label: str, label_num: str, offered: list[Candidate]) -> dict:
    """`label` names the chapters the videos cover (1-48), `label_num` the
    same as a title shows it (01-48)."""
    candidates = {c.id: c.record() for c in offered}
    body = [chapters, label, sorted((k, v["file"], v["size"]) for k, v in candidates.items())]
    return {"id": hashlib.sha1(json.dumps(body).encode()).hexdigest()[:6], "project": project,
            "chapters": chapters, "label": label, "label_num": label_num, "candidates": candidates}


def write_record(pdf_dir: Path, record: dict) -> None:
    write_json(pdf_dir / RECORD_NAME, record)


def read_record(pdf_dir: Path) -> dict | None:
    return read_json_or(pdf_dir / RECORD_NAME, None)


def _credit_line(found: dict) -> str:
    parts = [f"story {', '.join(found['story'])}" if found.get("story") else "",
             f"art {', '.join(found['art'])}" if found.get("art") else ""]
    known = "; ".join(p for p in parts if p)
    return known or "not known - the description leaves them out; never name anyone yourself"


def text_lines(identity: dict, found: dict, story: dict, record: dict, part_ids: list[str], index: int,
               total: int) -> list[str]:
    """Part `index` of `total`: on the first, everything; on the others,
    which images it holds."""
    offered = record["candidates"]
    panels = sum(1 for c in offered.values() if c["kind"] == "panel")
    lines = [
        f"project_name: {identity['project_name']}",
        f"manga: {found.get('title') or identity['manga_name']}",
        f"english_title: {found.get('english_title') or 'none known'}",
        f"manga_url: {identity['manga_url']}",
        f"credits: {_credit_line(found)}",
        f"videos: every chapter's video and every long video of this manga share this one upload set - "
        f"the title gets its chapters added (for example ' ({record['label_num']})'), so write for the "
        f"whole series, not one chapter",
        f"chapters offered: {', '.join(record['chapters'])}",
        f"images: {len(offered)} - after this text, one image per PDF page, its id stamped at its foot: "
        f"{panels} panels (the largest of each chapter) and {len(offered) - panels} colour pages",
    ]
    if total > 1:
        lines.append(f"part {index} of {total}: images {part_ids[0]} to {part_ids[-1]}"
                     + (" - the reply skeleton is on part 1" if index > 1 else ""))
    if index > 1:
        return lines
    lines.append("")
    if story["memory"]:
        lines.append(f"Story so far, after chapter {story['memory_from']} (from the memory written with each "
                     f"chapter's narration):")
        lines += story["memory"]
    else:
        lines.append("Story so far: none written yet.")
    if story["opening"]:
        lines += ["", f"How the story begins - chapter {story['opening_from']}'s narration:", story["opening"]]
    lines += ["", "The images offered, with the narration read over each panel:"]
    for image_id, c in offered.items():
        said = story["lines"].get(image_id)
        what = ("colour page" if c["kind"] == "page" else "colour panel" if c["colour"] else "panel")
        lines.append(f"{image_id} ({what}, {c['size'][0]}x{c['size'][1]})" + (f": {said}" if said else ""))
    lines += ["", "Reply skeleton - fill it in (three sets, A, B and C, each a different angle on the hook) and",
              "reply with it as one JSON code block:"]
    lines += skeleton(record["id"]).splitlines()
    return lines


def skeleton(upload_id: str) -> str:
    """The reply with every field in place and nothing filled in - a tile or a
    label to a line, so the text page's wrap never splits one."""
    tile = '{"image": "", "subject": [0, 0, 0, 0], "framing": "medium"}'
    lines = ["{", f'  "upload": "{upload_id}",', '  "sets": [']
    for n, letter in enumerate(LETTERS):
        lines += ["    {", f'      "letter": "{letter}",', '      "angle": "",', '      "title": "",',
                  '      "thumbnail": {', '        "tiles": [', f"          {tile},", f"          {tile}", "        ],",
                  '        "labels": [', '          {"text": "", "tile": 1}', "        ],", '        "badge": true',
                  "      }", "    }" + ("," if n < len(LETTERS) - 1 else "")]
    lines += ["  ],", '  "description": {"hook": ["", ""], "hashtags": []},', '  "problems": []', "}"]
    return "\n".join(lines)
