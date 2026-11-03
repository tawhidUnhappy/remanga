"""What one chapter's narration hand-off costs in tokens, part by part, on both routes.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-narration-eval/tokens.py PROJECT CHAPTER OUT_DIR \
        [--tokenizer tokenizer.json] [--page-tokens 560] [--reply narration.json] [--json result.json]

Gemini route - what the user uploads, and what comes back:
  prompt     prompts/narration.md, as text
  pdf text   the PDF's text pages as Gemini extracts them (pdftotext); the PDF is built by remanga's own
             code into OUT_DIR, never into the project
  pdf pages  every page of the PDF at a fixed price - Gemini 3 bills a PDF page 560 tokens at its default
             media resolution whatever the page shows (Gemini 2.x: 258), text pages included
  reply      the chapter's narration.json (or --reply): its narration section and its memory section
Claude route - what Claude reads and writes when it narrates the chapter itself:
  sheets     the pages two a sheet at 620 px (overlay.py), one token per 28x28-pixel patch after the
             long edge is brought down to 1568 px and the image to about 1,600 tokens (the standard tier)
  memory     the story so far it reads; the rows (a line per panel) and the memory it writes

Text is counted with a tokenizer.json when one is given (Gemma 3's uses Gemini's own vocabulary) - through
the `tokenizers` package, or through uv when this environment has no such package - and estimated at four
characters a token otherwise."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from remanga.config import RemangaConfig
from remanga.json_io import read_json_or
from remanga.narration import PROMPT_PATH, panel_files, read_reply
from remanga.paths import get_chapter_dir, get_narration_path
from remanga.pdf import build_panels_pdf
from remanga.pdf.manifest_info import MEMORY_KEY
from remanga.workflow.pdf import pdf_info

CHARS_PER_TOKEN = 4
SHEET_PER, SHEET_WIDTH = 2, 620      # overlay.py's reading sheets
CLAUDE_EDGE, CLAUDE_MAX, PATCH = 1568, 1600, 28

_COUNT = """import json, sys
from tokenizers import Tokenizer
tok = Tokenizer.from_file(sys.argv[1])
print(json.dumps([len(tok.encode(t, add_special_tokens=False).ids) for t in json.load(sys.stdin)]))"""


def token_counter(tokenizer: Path | None):
    """(count(texts) -> [tokens], what counted them)."""
    if tokenizer is None:
        return (lambda texts: [math.ceil(len(t) / CHARS_PER_TOKEN) for t in texts]), "estimated, 4 chars a token"
    try:
        from tokenizers import Tokenizer
    except ImportError:
        from remanga.tool_envs.install import uv_bin

        uv = str(uv_bin() or shutil.which("uv") or "uv")

        def count(texts: list[str]) -> list[int]:
            run = subprocess.run([uv, "run", "--no-project", "--quiet", "--with", "tokenizers", "python", "-I",
                                  "-c", _COUNT, str(tokenizer)], input=json.dumps(texts), capture_output=True,
                                 text=True, check=True)
            return json.loads(run.stdout)
        return count, tokenizer.name
    tok = Tokenizer.from_file(str(tokenizer))
    return (lambda texts: [len(tok.encode(t, add_special_tokens=False).ids) for t in texts]), tokenizer.name


def pdf_pages(path: Path) -> int:
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    return int(next(line.split()[-1] for line in out.splitlines() if line.startswith("Pages:")))


def claude_image_tokens(width: int, height: int) -> int:
    scale = min(1.0, CLAUDE_EDGE / max(width, height))
    w, h = width * scale, height * scale
    patches = math.ceil(w / PATCH) * math.ceil(h / PATCH)
    if patches > CLAUDE_MAX:
        shrink = math.sqrt(CLAUDE_MAX / patches)
        patches = math.ceil(w * shrink / PATCH) * math.ceil(h * shrink / PATCH)
    return patches


def reading_sheets(project: str, chapter: str) -> list[tuple[int, int]]:
    """The size of every 2-a-sheet reading sheet overlay.py draws for the chapter."""
    chapter_dir = get_chapter_dir(project, chapter)
    pages = (read_json_or(chapter_dir / "crops.json", {}) or {}).get("pages") or []
    tiles = []
    for page in pages:
        with Image.open(chapter_dir / "pages" / page["page_filename"]) as im:
            w, h = im.size
        width = SHEET_WIDTH * (2 if w > 2000 else 1)
        tiles.append((width, round(h * width / w)))
    sheets = []
    for s in range(0, len(tiles), SHEET_PER):
        group = tiles[s:s + SHEET_PER]
        sheets.append((sum(t[0] for t in group) + 10 * (len(group) - 1), max(t[1] for t in group) + 30))
    return sheets


def measure(project: str, chapter: str, out_dir: Path, count, page_tokens: int, reply: Path | None) -> dict:
    config = RemangaConfig.load()
    panels = panel_files(project, chapter)
    info, source = pdf_info(project, chapter, config)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    parts = build_panels_pdf(panels, out_dir, config.pdf.max_mb, info)
    pages = sum(pdf_pages(part) for part in parts)
    native = "\n".join(subprocess.run(["pdftotext", str(part), "-"], capture_output=True, text=True,
                                      check=True).stdout for part in parts)

    reply = reply or get_narration_path(project, chapter)
    doc, memory = read_reply(reply) if reply.exists() and reply.stat().st_size else ({}, None)
    rows = [f"{e['panel']} | {e['text']}" if not e.get("skip") else f"{e['panel']} | skip {e['skip']}"
            for e in (doc or {}).get("panels") or []]
    texts = {
        "prompt": PROMPT_PATH.read_text(encoding="utf-8"),
        "pdf_text": native,
        "story_so_far": ("\n".join(info[MEMORY_KEY]) if isinstance(info.get(MEMORY_KEY), list)
                         else json.dumps(info.get(MEMORY_KEY) or {}, indent=2, ensure_ascii=False)),
        "reply_narration": json.dumps({"narration": doc or {}}, indent=2, ensure_ascii=False),
        "narration_words": "\n".join(e.get("text") or "" for e in (doc or {}).get("panels") or []),
        "reply_memory": json.dumps({"memory": memory or {}}, indent=2, ensure_ascii=False),
        "rows": "\n".join(rows),
    }
    tokens = dict(zip(texts, count(list(texts.values())), strict=False))
    sheets = reading_sheets(project, chapter)
    result = {
        "project": project, "chapter": str(chapter), "panels": len(panels), "story_from": source,
        "gemini": {
            "prompt": tokens["prompt"], "pdf_text": tokens["pdf_text"],
            "pdf_pages": pages, "text_pages": pages - len(panels), "page_tokens": pages * page_tokens,
            "reply_narration": tokens["reply_narration"], "reply_memory": tokens["reply_memory"],
            "narration_only": tokens["narration_words"],
        },
        "claude": {
            "sheets": len(sheets), "sheet_tokens": sum(claude_image_tokens(w, h) for w, h in sheets),
            "memory_in": tokens["story_so_far"], "rows_out": tokens["rows"],
            "memory_out": tokens["reply_memory"], "prompt_once": tokens["prompt"],
        },
    }
    g, c = result["gemini"], result["claude"]
    g["total_in"] = g["prompt"] + g["pdf_text"] + g["page_tokens"]
    g["total_out"] = g["reply_narration"] + g["reply_memory"]
    c["total_in"] = c["sheet_tokens"] + c["memory_in"]
    c["total_out"] = c["rows_out"] + c["memory_out"]
    return result


def report(r: dict, counted_by: str, page_tokens: int) -> str:
    g, c = r["gemini"], r["claude"]
    rows = [
        f"{r['project']} chapter {r['chapter']}: {r['panels']} panels; story so far from chapter "
        f"{r['story_from'] or '-'}; text counted with {counted_by}",
        "GEMINI (one upload, one reply)",
        f"  in   prompt                       {g['prompt']:>8,}",
        f"       PDF text (extracted)         {g['pdf_text']:>8,}",
        f"       PDF pages {g['pdf_pages']:>4} x {page_tokens:<4}         {g['page_tokens']:>8,}"
        f"   ({g['text_pages']} of them text pages)",
        f"       total in                     {g['total_in']:>8,}",
        f"  out  narration section            {g['reply_narration']:>8,}   (the narration alone "
        f"{g['narration_only']:,})",
        f"       memory section               {g['reply_memory']:>8,}",
        f"       total out                    {g['total_out']:>8,}",
        "CLAUDE (start to end)",
        f"  in   sheets {c['sheets']:>3} (2 pages each)      {c['sheet_tokens']:>8,}",
        f"       story so far                 {c['memory_in']:>8,}",
        f"       total in                     {c['total_in']:>8,}   (+ the prompt once a session, "
        f"{c['prompt_once']:,})",
        f"  out  rows                         {c['rows_out']:>8,}",
        f"       memory                       {c['memory_out']:>8,}",
        f"       total out                    {c['total_out']:>8,}",
    ]
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("chapter")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--tokenizer", type=Path)
    parser.add_argument("--page-tokens", type=int, default=560)
    parser.add_argument("--reply", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    count, counted_by = token_counter(args.tokenizer)
    result = measure(args.project, args.chapter, args.out_dir, count, args.page_tokens, args.reply)
    print(report(result, counted_by, args.page_tokens))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
