"""A chapter's narration.json from the narration Claude wrote: one JSON object a line
({"panel", "text"} or {"panel", "skip", "text": ""}) plus the memory section, checked
against the cut panels and then by Make video's own check.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py \
        PROJECT CHAPTER panels.jsonl memory.json

Refuses (writes nothing) when the panel ids are not exactly the chapter's panels, in order."""
import json
import sys
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.paths import get_chapter_dir
from remanga.workflow.video import check_chapter

project, chapter, rows_file, memory_file = sys.argv[1:5]
rows = [json.loads(line) for line in Path(rows_file).read_text(encoding="utf-8").splitlines() if line.strip()]
chapter_dir = get_chapter_dir(project, chapter)
ids = [f.stem for f in sorted((chapter_dir / "panels").glob("*.png"))]
got = [row["panel"] for row in rows]
if got != ids:
    import difflib
    print("\n".join(difflib.unified_diff(ids, got, "panels/", rows_file, lineterm="")))
    sys.exit(f"{len(got)} rows for {len(ids)} panels - not written")
doc = {"narration": {"chapter": str(chapter), "problems": [], "panels": rows},
       "memory": json.loads(Path(memory_file).read_text(encoding="utf-8"))}
(chapter_dir / "narration.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
words = sum(len(row.get("text", "").split()) for row in rows)
result = check_chapter(project, chapter, RemangaConfig.load())
print(f"chapter {chapter}: {len(rows)} panels, {words} words -> {result['state']}")
for line in result["errors"] + result["warnings"]:
    print("  -", line)
