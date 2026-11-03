"""A chapter's narration.json from the narration Claude wrote, checked against the cut panels and then
by Make video's own check - and, before writing it, the story so far it continues.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py PROJECT CHAPTER --story
    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py PROJECT CHAPTER reply.json
    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py \
        PROJECT CHAPTER rows.txt memory.json

--story prints what the chapter's PDF would give an LLM: the story so far (every earlier chapter's memory,
folded) and the threads still open - read that instead of an earlier chapter's narration.json.
reply.json is exactly what an LLM answers the panel PDF with (prompts/narration.md):
{"narration": {"chapter", "problems", "panels": {ID: text or "skip REASON"}}, "memory": {...}}. Or, written
as you go: rows.txt holds a line per panel, in order - `001_004_02 | text` or `001_004_01 | skip REASON`
(credits, ad, blank, duplicate, title, merged, merged_prev); blank lines and # comments are ignored; a
.jsonl file of {"panel", "text"} / {"panel", "skip", "text": ""} objects works too - with the memory in
memory.json: what this chapter changed (summary, events, characters, places, terms, threads), never the
whole story again. Refuses (writes nothing) when the panel ids are not exactly the chapter's panels, in
order, or the memory can't be folded. The file is written whole and then renamed into place, so a render
waiting on it never reads half of it."""
import json
import os
import re
import sys
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.json_io import json_from_reply
from remanga.narration import SKIP_REASONS, memory_problems, panel_entries, story_lines, story_so_far
from remanga.paths import get_chapter_dir
from remanga.workflow.video import check_chapter

SKIPS = set(SKIP_REASONS)


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


if len(sys.argv) not in (4, 5):
    sys.exit(__doc__)
project, chapter, rows_file = sys.argv[1:4]
if rows_file == "--story":
    story, through = story_so_far(project, chapter)
    print(f"Story so far, after chapter {through}:" if story else "Story so far: none - the first chapter.")
    print("\n".join(story_lines(story) if story else []))
    sys.exit(0)
if len(sys.argv) == 4:   # the whole reply, as an LLM gives it
    reply = json_from_reply(Path(rows_file).read_text(encoding="utf-8"))
    rows, memory = panel_entries(reply["narration"]["panels"]), reply.get("memory") or {}
else:
    rows, memory = read_rows(Path(rows_file)), json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
errors, warnings = memory_problems(memory)
if errors:
    sys.exit("memory: " + "; ".join(errors) + " - not written")
chapter_dir = get_chapter_dir(project, chapter)
ids = [f.stem for f in sorted((chapter_dir / "panels").glob("*.png"))]
got = [row["panel"] for row in rows]
if got != ids:
    import difflib
    print("\n".join(difflib.unified_diff(ids, got, "panels/", rows_file, lineterm="")))
    sys.exit(f"{len(got)} rows for {len(ids)} panels - not written")
doc = {"narration": {"chapter": str(chapter), "problems": [], "panels": rows}, "memory": memory}
target = chapter_dir / "narration.json"
partial = target.with_name(f".{target.name}.{os.getpid()}.tmp")
partial.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
partial.replace(target)
words = sum(len(row.get("text", "").split()) for row in rows)
result = check_chapter(project, chapter, RemangaConfig.load())
print(f"chapter {chapter}: {len(rows)} panels, {words} words -> {result['state']}")
for line in warnings + result["errors"] + result["warnings"]:
    print("  -", line)
