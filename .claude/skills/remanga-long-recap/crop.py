"""Panel cropping for Claude, from the raw downloads - page manga and webtoon strips alike.
Look at sheets with coordinates on them, write a small JSON plan, apply, check.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/crop.py show  P CH OUT [first-last]
    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/crop.py apply P CH plan.json
    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/crop.py check P CH OUT

show   Page manga: 4 pages a sheet, the current marks numbered in reading order on a 0-1000 grid, the
       hints dashed (F1 a figure, B1 a balloon crossing a box - from what MAGI saw, chapters/N/found.json)
       and printed with their suggestions, plus notes on thin strips, duplicate and nested boxes.
       Webtoon: the strip in columns of 2,400 rows with a ruler in CHAPTER rows; every cut is a red line
       labelled with its row (thin green: the detector's own cuts, when the marks are saved ones).
apply  The plan is the JSON an LLM answers the crop PDF with (prompts/crop.md) - only the pages to change:
           {"pages": [
             {"page": 6, "panels": [[1, 649, 580, 932], [1, 0, 580, 573]]},   measured [ymin,xmin,ymax,xmax]
             {"page": 7, "panels": [1, "3+4", 2]},                              boxes drawn now; + joins
             {"page": 8, "exact": true, "panels": ["2+B1", 1, "F1"]},           hints, like box numbers
             {"page": 13, "panels": []}]}                                       no panels: credits, ads
       Webtoon - edits to the saved marks (else the proposal), chapter rows read off the ruler:
           {"edits": [{"split": 45210}, {"join": 81738}, {"move": [81738, 81900]}, {"drop": 1248},
                      {"add": [1000, 2400]}]}
       The older plain lines (`page 7: 1 / 3+4 / 2`, `join 81738`) are read too.
check  Cuts the panels (remanga's own cutter), writes contact sheets of them to OUT and lists any panel
       cut much smaller or larger than its mark (the snapper's failures) - look at those.
Nothing is touched outside the chapter.

The format is remanga's crop plan (remanga/crop_plan/) - the same one an LLM answers the crop PDF in
(prompts/crop.md), read and drawn by the same code."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from remanga.config import RemangaConfig
from remanga.crop_plan import apply_edits, apply_page_lines, cut_report, cuts_of, page_record, read_reply, strip_now
from remanga.crop_plan.found import read_found
from remanga.crop_plan.handoff import page_record_of
from remanga.crop_plan.sheets import draw_page, strip_sheets
from remanga.layouts import layout_for
from remanga.paths import get_chapter_dir, get_crops_path


def is_strip(project: str, chapter: str) -> bool:
    return layout_for(project, chapter).name == "long_strip"


def show_pages(project: str, chapter: str, out: Path, first: int, last: int) -> None:
    record = page_record_of(chapter, page_record(project, chapter), read_found(project, chapter))
    pages = [p for p in record["pages"] if first <= p["page_index"] <= last]
    for page in pages:
        for hint in page.get("hints", []):
            print(f"page {page['page_index']}: {hint['label']} {hint['why']}"
                  + (f" - suggested {hint['suggest']}" + (" (exact)" if hint["exact"] else "") if hint["suggest"]
                     else ""))
        for note in page.get("notes", []):
            print(f"page {page['page_index']}: {note}")
    pages_dir = get_chapter_dir(project, chapter) / "pages"
    head = ImageFont.load_default(size=22)
    for start in range(0, len(pages), 4):
        group = pages[start:start + 4]
        tiles = []
        for page in group:
            with Image.open(pages_dir / page["page_filename"]) as image:
                boxes = [p["box_1000"] for p in page.get("panels", []) if p.get("box_1000")]
                tiles.append(draw_page(image, boxes, width=460, hints=page.get("hints", ())))
        sheet = Image.new("RGB", (sum(t.width for t in tiles) + 10 * (len(tiles) - 1),
                                  max(t.height for t in tiles) + 30), "white")
        x = 0
        for page, tile in zip(group, tiles, strict=True):
            ImageDraw.Draw(sheet).text((x + 4, 2), f"page {page['page_index']}  ({page['page_filename']})  "
                                                   f"{len(page.get('panels', []))} marks"
                                                   + ("  exact" if page.get("exact") else ""), fill="black", font=head)
            sheet.paste(tile, (x, 30))
            x += tile.width + 10
        path = out / f"pages_{group[0]['page_index']:03d}-{group[-1]['page_index']:03d}.jpg"
        sheet.save(path, quality=85)
        print(path)


def apply_pages(project: str, chapter: str, plan) -> None:
    current = page_record(project, chapter)
    # The boxes as show drew them, with their hints - what the plan's numbers and labels mean.
    base = page_record_of(chapter, current, read_found(project, chapter))
    outcome = apply_page_lines(base, current, plan.pages, src="manual")
    if outcome.errors:
        raise SystemExit("Nothing applied:\n" + "\n".join(f"  {e}" for e in outcome.errors))
    for line in plan.pages:
        panels = next(p for p in outcome.record["pages"] if p["page_index"] == line.page)["panels"]
        print(f"page {line.page}: {len(panels)} panel(s)" + (" exact" if line.exact else ""))
    for warning in outcome.warnings:
        print(f"  ! {warning}")
    get_crops_path(project, chapter).write_text(json.dumps(outcome.record, indent=1, ensure_ascii=False),
                                                encoding="utf-8")


def show_strip(project: str, chapter: str, out: Path) -> None:
    now = strip_now(project, chapter)
    compare = cuts_of(now.proposed) if now.saved else []
    for number, sheet in enumerate(strip_sheets(now.view, now.panels, rows=2400, width=300, per_sheet=6,
                                                compare=compare)):
        path = out / f"strip_{number:02d}.jpg"
        sheet.save(path, quality=82)
        print(path)
    print(f"{len(cuts_of(now.panels))} cut(s) " + (f"saved ({len(compare)} proposed, green)" if now.saved
                                                   else "proposed, no saved marks yet"))


def apply_strip(project: str, chapter: str, plan) -> None:
    from remanga.plugins.long_strip.marks import write_marks

    now = strip_now(project, chapter)
    outcome = apply_edits(now.panels, plan.edits, now.height)
    if outcome.errors:
        raise SystemExit("Nothing applied:\n" + "\n".join(f"  {e}" for e in outcome.errors))
    for line in outcome.changed:
        print(line)
    write_marks(project, chapter, now.sources, [list(p) for p in outcome.panels], now.height)


def check(project: str, chapter: str, out: Path) -> None:
    from remanga.workflow.panels import cut_panels

    config = RemangaConfig.load()
    cut_panels(project, chapter, config, force=True)
    panels = sorted((get_chapter_dir(project, chapter) / "panels").glob("*.png"))
    font = ImageFont.load_default(size=14)
    for start in range(0, len(panels), 24):
        group = panels[start:start + 24]
        sheet = Image.new("RGB", (6 * 240, ((len(group) + 5) // 6) * 300), (90, 90, 90))
        d = ImageDraw.Draw(sheet)
        for i, path in enumerate(group):
            im = Image.open(path).convert("RGB")
            size = f"{im.width}x{im.height}"
            im.thumbnail((232, 272))
            x, y = (i % 6) * 240, (i // 6) * 300
            sheet.paste(im, (x + 4, y + 24))
            d.text((x + 4, y + 4), f"{path.stem}  {size}", fill="yellow", font=font)
        target = out / f"panels_{start // 24:02d}.jpg"
        sheet.save(target, quality=82)
        print(target)
    print(f"{len(panels)} panel(s) cut")
    if not is_strip(project, chapter):
        found = cut_report(project, chapter)
        if found:
            print(f"{len(found)} page(s) or panel(s) worth a look:")
            print("\n".join(f"  {line}" for line in found))


def main() -> None:
    if len(sys.argv) < 5 or sys.argv[1] not in ("show", "apply", "check"):
        raise SystemExit(__doc__)
    action, project, chapter, target = sys.argv[1:5]
    strip = is_strip(project, chapter)
    if action == "apply":
        plan = read_reply(Path(target).read_text(encoding="utf-8"))
        if plan.chapter is not None and plan.chapter != str(chapter):
            plan.errors.append(f"the plan says chapter {plan.chapter}, not {chapter}")
        if plan.errors:
            raise SystemExit("Nothing applied:\n" + "\n".join(f"  {e}" for e in plan.errors))
        (apply_strip if strip else apply_pages)(project, chapter, plan)
        return
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    if action == "check":
        check(project, chapter, out)
    elif strip:
        show_strip(project, chapter, out)
    else:
        first, _, last = (sys.argv[5] if len(sys.argv) > 5 else "1-9999").partition("-")
        show_pages(project, chapter, out, int(first), int(last or first))


if __name__ == "__main__":
    main()
