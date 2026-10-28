"""Panel cropping for Claude, from the raw downloads - page manga and webtoon strips alike.
Look at sheets with coordinates on them, write a few lines of plain text, apply, check.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/crop.py show  P CH OUT [first-last]
    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/crop.py apply P CH plan.txt
    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/crop.py check P CH OUT

show   Page manga: 4 pages a sheet, the current marks numbered in reading order on a 0-1000 grid.
       Webtoon: the strip in columns of 2,400 rows with a ruler in CHAPTER rows; every proposed cut
       is a red line labelled with its row (green: a cut of saved marks, when there are some).
apply  Page manga - a line per page to set, boxes [ymin,xmin,ymax,xmax] in thousandths, reading order:
           page 6: 1,649,580,932 / 1,0,580,573 / 576,293,1000,935
           page 5 exact: 15,0,362,822 / 365,330,642,935      (exact = overlap kept, no snapping)
           page 13: none                                     (no panels: credits, ads)
       Webtoon - edits to the saved marks (else the proposal), chapter rows read off the ruler:
           split 45210          a new cut at row 45210
           join 81738           the cut nearest 81738 goes (the two panels become one)
           move 81738 81900     the cut nearest 81738 moves to 81900
           drop 1248            the panel holding row 1248 goes (credits)
           add 1000 2400        a panel of its own (overlaps allowed)
check  Cuts the panels (remanga's own cutter), writes contact sheets of them to OUT and lists any panel
       cut much smaller or larger than its mark (the snapper's failures) - look at those.
Lines starting with # are comments. Nothing is touched outside the chapter."""

from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from overlay import draw_page  # noqa: E402  (this folder's page renderer)

from remanga.config import RemangaConfig  # noqa: E402
from remanga.layouts import layout_for  # noqa: E402
from remanga.paths import get_chapter_dir  # noqa: E402

COLUMN_ROWS = 2400
COLUMN_WIDTH = 300
COLUMNS = 6
NEAREST = 400     # how far a join/move looks for the cut it names
SIZE_RANGE = (0.7, 1.5)   # cut area / marked area outside this is reported by check


def is_strip(project: str, chapter: str) -> bool:
    return layout_for(project, chapter).name == "long_strip"


# ---- page manga ----------------------------------------------------------------------------------

def crops_path(project: str, chapter: str) -> Path:
    return get_chapter_dir(project, chapter) / "crops.json"


def page_record(project: str, chapter: str) -> dict:
    path = crops_path(project, chapter)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    pages = sorted(p for p in (get_chapter_dir(project, chapter) / "pages").iterdir() if p.is_file())
    return {"chapter": chapter, "marks_format": 2,
            "pages": [{"page_index": i, "page_filename": p.name, "is_story_page": True, "panels": [],
                       "user_decided": False} for i, p in enumerate(pages, 1)]}


def show_pages(project: str, chapter: str, out: Path, first: int, last: int) -> None:
    record = page_record(project, chapter)
    pages = [p for p in record["pages"] if first <= p["page_index"] <= last]
    chapter_dir = get_chapter_dir(project, chapter)
    head = ImageFont.load_default(size=22)
    for start in range(0, len(pages), 4):
        group = pages[start:start + 4]
        tiles = [draw_page(chapter_dir, p, 460) for p in group]
        sheet = Image.new("RGB", (sum(t.width for t in tiles) + 10 * (len(tiles) - 1), max(t.height for t in tiles) + 30),
                          "white")
        x = 0
        for page, tile in zip(group, tiles, strict=True):
            ImageDraw.Draw(sheet).text((x + 4, 2), f"page {page['page_index']}  ({page['page_filename']})  "
                                                   f"{len(page.get('panels', []))} marks", fill="black", font=head)
            sheet.paste(tile, (x, 30))
            x += tile.width + 10
        path = out / f"pages_{group[0]['page_index']:03d}-{group[-1]['page_index']:03d}.jpg"
        sheet.save(path, quality=85)
        print(path)


def apply_pages(project: str, chapter: str, lines: list[str]) -> None:
    record = page_record(project, chapter)
    by_index = {p["page_index"]: p for p in record["pages"]}
    for line in lines:
        m = re.fullmatch(r"page\s+(\d+)\s*(exact)?\s*:\s*(.*)", line)
        if not m:
            raise SystemExit(f"Not a page line: {line!r}")
        page = by_index.get(int(m.group(1)))
        if page is None:
            raise SystemExit(f"Chapter {chapter} has no page {m.group(1)}")
        boxes = [] if m.group(3).strip().lower() == "none" else [
            [int(v) for v in box.split(",")] for box in m.group(3).split("/")]
        for box in boxes:
            if len(box) != 4 or not (0 <= box[0] < box[2] <= 1000 and 0 <= box[1] < box[3] <= 1000):
                raise SystemExit(f"Page {m.group(1)}: {box} is not ymin,xmin,ymax,xmax in 0-1000")
        page["panels"] = [{"panel_id": i, "box_1000": box, "src": "manual"} for i, box in enumerate(boxes, 1)]
        page["is_story_page"] = bool(boxes)
        page["user_decided"] = True
        page["custom_order"] = True
        if m.group(2):
            page["exact"] = True
        else:
            page.pop("exact", None)
        print(f"page {m.group(1)}: {len(boxes)} panel(s)" + (" exact" if m.group(2) else ""))
    crops_path(project, chapter).write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")


# ---- webtoon strips ------------------------------------------------------------------------------

def strip_state(project: str, chapter: str):
    from remanga.plugins.long_strip.build import proposed_marks
    from remanga.plugins.long_strip.layout import source_pages
    from remanga.plugins.long_strip.marks import read_marks
    from remanga.plugins.long_strip.runs import runs_of
    from remanga.plugins.long_strip.tiles import StripView

    sources = source_pages(project, chapter)
    view = StripView(runs_of(sources))
    saved = read_marks(project, chapter, sources)
    proposed, _ = proposed_marks(view)
    return sources, view, saved, [(m[0], m[1]) for m in proposed]


def cuts_of(marks: list[tuple[int, int]]) -> list[int]:
    marks = sorted(marks)
    return [round((a[1] + b[0]) / 2) for a, b in itertools.pairwise(marks)]


def show_strip(project: str, chapter: str, out: Path) -> None:
    _, view, saved, proposed = strip_state(project, chapter)
    red, green = cuts_of(proposed), cuts_of(saved or [])
    font = ImageFont.load_default(size=13)
    columns = []
    for index, run in enumerate(view.runs):
        image = view.image(index)
        for top in range(0, run.height, COLUMN_ROWS):
            piece = image.crop((0, top, run.width, min(run.height, top + COLUMN_ROWS)))
            scale = COLUMN_WIDTH / run.width
            piece = piece.resize((COLUMN_WIDTH, max(1, round(piece.height * scale))))
            col = Image.new("RGB", (COLUMN_WIDTH + 64, round(COLUMN_ROWS * scale) + 4), "white")
            col.paste(piece, (64, 0))
            d = ImageDraw.Draw(col)
            first = run.top + top
            for row in range(first - first % 200 + 200, first + COLUMN_ROWS, 200):
                y = round((row - first) * scale)
                d.line((48, y, 64, y), fill="black")
                d.text((2, y - 7), str(row), fill="black", font=font)
            for rows, color in ((green, (0, 170, 0)), (red, (230, 0, 0))):
                for row in rows:
                    if first <= row < first + COLUMN_ROWS:
                        y = round((row - first) * scale)
                        d.line((64, y, col.width, y), fill=color, width=3)
                        d.rectangle((64, y - 9, 64 + 52, y + 7), fill=color)
                        d.text((66, y - 8), str(row), fill="white", font=font)
            columns.append(col)
    for start in range(0, len(columns), COLUMNS):
        group = columns[start:start + COLUMNS]
        sheet = Image.new("RGB", (sum(c.width + 8 for c in group), max(c.height for c in group)), (90, 90, 90))
        x = 0
        for col in group:
            sheet.paste(col, (x, 0))
            x += col.width + 8
        path = out / f"strip_{start // COLUMNS:02d}.jpg"
        sheet.save(path, quality=82)
        print(path)
    print(f"{len(red)} proposed cut(s)" + (f", {len(green)} saved" if saved else ", no saved marks yet"))


def apply_strip(project: str, chapter: str, lines: list[str]) -> None:
    from remanga.plugins.long_strip.marks import write_marks

    sources, view, saved, proposed = strip_state(project, chapter)
    marks = sorted((m[0], m[1]) for m in (saved or proposed))

    def boundary(row: int) -> int:
        best = min(range(len(marks) - 1), key=lambda i: abs((marks[i][1] + marks[i + 1][0]) / 2 - row))
        if abs((marks[best][1] + marks[best + 1][0]) / 2 - row) > NEAREST:
            raise SystemExit(f"No cut within {NEAREST} rows of {row}")
        return best

    def holding(row: int) -> int:
        for i, (t, b) in enumerate(marks):
            if t <= row < b:
                return i
        raise SystemExit(f"No panel holds row {row}")

    for line in lines:
        op, *args = line.split()
        nums = [int(a) for a in args]
        if op == "split":
            i = holding(nums[0])
            t, b = marks[i]
            marks[i:i + 1] = [(t, nums[0]), (nums[0], b)]
        elif op == "join":
            i = boundary(nums[0])
            marks[i:i + 2] = [(marks[i][0], marks[i + 1][1])]
        elif op == "move":
            i = boundary(nums[0])
            marks[i], marks[i + 1] = (marks[i][0], nums[1]), (nums[1], marks[i + 1][1])
        elif op == "drop":
            del marks[holding(nums[0])]
        elif op == "add":
            marks.append((nums[0], nums[1]))
        else:
            raise SystemExit(f"Unknown edit: {line!r}")
        marks.sort()
        print(f"{line}  ->  {len(marks)} panels")
    write_marks(project, chapter, sources, [[t, b] for t, b in marks], view.runs[-1].bottom)


# ---- both ----------------------------------------------------------------------------------------

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
        size_report(project, chapter)


def size_report(project: str, chapter: str) -> None:
    """Cut panels much smaller or larger than their mark - the snapper's failure shape (a sliver, or a
    panel grown into its neighbour or the page's blurb) under a mark that looks right on the sheets."""
    chapter_dir = get_chapter_dir(project, chapter)
    cuts: dict[int, list[Path]] = {}
    for path in sorted((chapter_dir / "panels").glob("*.png")):
        cuts.setdefault(int(path.stem.rsplit("_", 2)[1]), []).append(path)
    flagged = []
    for page in page_record(project, chapter)["pages"]:
        marks = [p["box_1000"] for p in page.get("panels", []) if "box_1000" in p]
        files = cuts.get(page["page_index"], [])
        if not marks or len(marks) != len(files):
            continue
        with Image.open(chapter_dir / "pages" / page["page_filename"]) as image:
            width, height = image.size
        for (y0, x0, y1, x1), path in zip(marks, files, strict=True):
            mark_w, mark_h = (x1 - x0) * width / 1000, (y1 - y0) * height / 1000
            with Image.open(path) as image:
                cut_w, cut_h = image.size
            area = cut_w * cut_h / max(1.0, mark_w * mark_h)
            if not SIZE_RANGE[0] <= area <= SIZE_RANGE[1]:
                flagged.append(f"  {path.stem}: marked {mark_w:.0f}x{mark_h:.0f}, "
                               f"cut {cut_w}x{cut_h} (area x{area:.2f})")
    if flagged:
        print(f"{len(flagged)} panel(s) cut much smaller or larger than marked - look at them:")
        print("\n".join(flagged))


def main() -> None:
    if len(sys.argv) < 5 or sys.argv[1] not in ("show", "apply", "check"):
        raise SystemExit(__doc__)
    action, project, chapter, target = sys.argv[1:5]
    strip = is_strip(project, chapter)
    if action == "apply":
        lines = [line.split("#", 1)[0].strip() for line in Path(target).read_text(encoding="utf-8").splitlines()]
        lines = [line for line in lines if line]
        (apply_strip if strip else apply_pages)(project, chapter, lines)
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
