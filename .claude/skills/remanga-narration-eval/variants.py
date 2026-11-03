"""The variants of one chapter's narration hand-off, side by side, for an LLM to answer each of them.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-narration-eval/variants.py PROJECT CHAPTER OUT_DIR \
        [--old WORKTREE]

Writes OUT_DIR/<variant>/ with the PDF(s) and the prompt each variant hands over:
  panels  the panel PDF and prompts/narration.md, exactly as `./run.sh pdf` makes them
  pages   the chapter's pages instead of its cut panels - every panel outlined on its page and labelled
          with its id - with the same text page, and the prompt's "What you receive" saying so
  old     (with --old WORKTREE, a git worktree of an earlier commit) the panel PDF and the prompt that
          commit made: its own code, run on the same project
The project must be a throwaway copy (projects/zz*): `old` runs that commit's own PDF step on it.
Run from the remanga repo root."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from remanga.config import RemangaConfig
from remanga.cropper.naming import panel_stem
from remanga.json_io import read_json_or
from remanga.narration import PROMPT_PATH
from remanga.paths import get_chapter_dir, get_pdf_dir
from remanga.pdf import build_image_pdf
from remanga.pdf.manifest_info import build_part_info, info_to_text_lines
from remanga.workflow.pdf import make_pdf, pdf_info

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MARK, INK = (254, 166, 43), (26, 18, 6)

# The pages variant's "What you receive": the first paragraph and the panel-id bullet, as they read for
# a PDF of pages.
PAGES_RECEIVE = [
    ("A PDF of one chapter's panels, already cut out and in reading order, one panel to a page (sometimes\n"
     "split into `panels_1.pdf`, `panels_2.pdf`, ...; wait for every part).",
     "A PDF of one chapter's pages, in reading order, one manga page to a PDF page (sometimes split into\n"
     "`pages_1.pdf`, `pages_2.pdf`, ...; wait for every part). Every panel on a page is outlined and\n"
     "labelled with its ID in its top-left corner. You narrate the panels, never a page as a whole: the\n"
     "page shows you how its panels sit together - which share a tier, where a bubble's tail runs, who\n"
     "faces whom across the gutter."),
    ("The images that\n  follow are those panels, in that order.",
     "The images that\n  follow are the pages those panels are on, each panel's box labelled with its ID."),
]


def page_marks(chapter_dir: Path, chapter: str) -> list[tuple[Path, list[tuple[str, list[int]]]]]:
    """Every page with its panels: (page file, [(panel id, box_1000)]) - the ids the cut panels carry."""
    crops = read_json_or(chapter_dir / "crops.json", {}) or {}
    out = []
    for page in crops.get("pages") or []:
        marks = [(panel_stem(chapter, page["page_index"], panel["panel_id"]), panel["box_1000"])
                 for panel in page.get("panels") or []]
        out.append((chapter_dir / "pages" / page["page_filename"], marks))
    return out


def draw_page(source: Path, marks: list[tuple[str, list[int]]], target: Path) -> None:
    im = Image.open(source).convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im)
    outline = max(3, round(min(w, h) / 300))
    font = ImageFont.truetype(FONT, max(16, round(min(w, h) / 40)))
    for label, (y0, x0, y1, x1) in marks:
        box = (x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000)
        d.rectangle(box, outline=MARK, width=outline)
        left, top, right, bottom = d.textbbox((0, 0), label, font=font)
        x, y = min(box[0] + outline, w - (right - left) - 8), min(box[1] + outline, h - (bottom - top) - 8)
        d.rectangle((x, y, x + right - left + 8, y + bottom - top + 8), fill=MARK)
        d.text((x + 4 - left, y + 4 - top), label, font=font, fill=INK)
    im.save(target, "JPEG", quality=92, subsampling=0)


def pages_variant(project: str, chapter: str, out: Path, config: RemangaConfig) -> list[Path]:
    chapter_dir = get_chapter_dir(project, chapter)
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)
    panels_of: dict[str, list[str]] = {}
    paths = []
    for source, marks in page_marks(chapter_dir, chapter):
        target = images / f"{source.stem}.jpg"
        draw_page(source, marks, target)
        panels_of[target.stem] = [label for label, _ in marks]
        paths.append(target)
    info, _ = pdf_info(project, chapter, config)
    every_panel = [p for stem in panels_of for p in panels_of[stem]]

    def text(full_ids: list[str], part_ids: list[str], index: int, total: int) -> list[str]:
        part_panels = [p for stem in part_ids for p in panels_of[stem]]
        return info_to_text_lines(build_part_info(info, every_panel, part_panels, index, total))

    parts = build_image_pdf(paths, out, config.pdf.max_mb, "pages", text, own_size=True, noun="pages")
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    for old, new in PAGES_RECEIVE:
        if old not in prompt:
            sys.exit(f"prompts/narration.md no longer says {old[:50]!r} - update PAGES_RECEIVE")
        prompt = prompt.replace(old, new)
    (out / "narration.md").write_text(prompt, encoding="utf-8")
    return parts


def panels_variant(project: str, chapter: str, out: Path, config: RemangaConfig) -> list[Path]:
    result = make_pdf(project, chapter, config)
    out.mkdir(parents=True, exist_ok=True)
    for part in result.parts:
        shutil.copy2(part, out / part.name)
    shutil.copy2(PROMPT_PATH, out / "narration.md")
    return [out / part.name for part in result.parts]


def old_variant(project: str, chapter: str, out: Path, worktree: Path) -> list[Path]:
    """That commit's own PDF step, run from this directory (projects/ and config.json are found from
    here) with its code first on the path."""
    code = ("import sys; from remanga.config import RemangaConfig; from remanga.workflow.pdf import make_pdf; "
            "print('\\n'.join(str(p) for p in make_pdf(sys.argv[1], sys.argv[2], RemangaConfig.load()).parts))")
    run = subprocess.run([sys.executable, "-P", "-c", code, project, chapter], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(worktree)}, check=True)
    out.mkdir(parents=True, exist_ok=True)
    parts = [Path(line) for line in run.stdout.splitlines() if line.endswith(".pdf")]
    for part in parts:
        shutil.copy2(part, out / part.name)
    shutil.copy2(worktree / "prompts" / "narration.md", out / "narration.md")
    return [out / part.name for part in parts]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("chapter")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--old", type=Path)
    args = parser.parse_args()
    if not args.project.startswith("zz"):
        sys.exit("Use a throwaway copy of the project (projects/zz*) - the old variant runs its PDF step on it.")
    config = RemangaConfig.load()
    made = {}
    if args.old:
        made["old"] = old_variant(args.project, args.chapter, args.out_dir / "old", args.old)
    made["panels"] = panels_variant(args.project, args.chapter, args.out_dir / "panels", config)
    made["pages"] = pages_variant(args.project, args.chapter, args.out_dir / "pages", config)
    for old in get_pdf_dir(args.project, args.chapter).glob("p*_*.pdf"):
        old.unlink()
    print(json.dumps({name: [str(p) for p in parts] for name, parts in made.items()}, indent=2))


if __name__ == "__main__":
    main()
