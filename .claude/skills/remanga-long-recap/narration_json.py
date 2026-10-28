"""A chapter's narration.json from the narration Claude wrote, plus the memory section, checked
against the cut panels and then by Make video's own check.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py \
        PROJECT CHAPTER rows.txt memory.json

rows.txt holds a line per panel, in order - `001_004_02 | text` or `001_004_01 | skip REASON` (credits,
ad, blank, duplicate, title, merged); blank lines and # comments are ignored. A .jsonl file of
{"panel", "text"} / {"panel", "skip", "text": ""} objects works too.
Refuses (writes nothing) when the panel ids are not exactly the chapter's panels, in order. The file is
written whole and then renamed into place, so a render waiting on it never reads half of it."""
import json
import os
import re
import sys
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.paths import get_chapter_dir
from remanga.workflow.video import check_chapter

SKIPS = {"credits", "ad", "blank", "duplicate", "title", "merged"}


def read_rows(path: Path) -> list[dict]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]
    if lines and lines[0].startswith("{"):
        return [json.loads(line) for line in lines]
    rows = []
    for line in lines:
        panel, sep, text = (part.strip() for part in line.partition("|"))
        if not sep or not re.fullmatch(r"\d{3}_\d{3}_\d{2}", panel):
            sys.exit(f"Not 'PANEL_ID | text': {line[:70]!r}")
        skip = re.fullmatch(r"skip (\w+)", text)
        if skip and skip.group(1) not in SKIPS:
            sys.exit(f"{panel}: unknown skip {skip.group(1)!r} - one of {', '.join(sorted(SKIPS))}")
        rows.append({"panel": panel, "skip": skip.group(1), "text": ""} if skip else {"panel": panel, "text": text})
    return rows


project, chapter, rows_file, memory_file = sys.argv[1:5]
rows = read_rows(Path(rows_file))
chapter_dir = get_chapter_dir(project, chapter)
ids = [f.stem for f in sorted((chapter_dir / "panels").glob("*.png"))]
got = [row["panel"] for row in rows]
if got != ids:
    import difflib
    print("\n".join(difflib.unified_diff(ids, got, "panels/", rows_file, lineterm="")))
    sys.exit(f"{len(got)} rows for {len(ids)} panels - not written")
doc = {"narration": {"chapter": str(chapter), "problems": [], "panels": rows},
       "memory": json.loads(Path(memory_file).read_text(encoding="utf-8"))}
target = chapter_dir / "narration.json"
partial = target.with_name(f".{target.name}.{os.getpid()}.tmp")
partial.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
partial.replace(target)
words = sum(len(row.get("text", "").split()) for row in rows)
result = check_chapter(project, chapter, RemangaConfig.load())
print(f"chapter {chapter}: {len(rows)} panels, {words} words -> {result['state']}")
for line in result["errors"] + result["warnings"]:
    print("  -", line)
