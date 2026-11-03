"""Pages with their crops.json boxes drawn (reading-order numbers) and a 0-1000 grid.

    .venv/bin/python -I overlay.py CHAPTER_DIR OUT_DIR PER_SHEET WIDTH [first-last page_index]

Review marks: 4 a sheet at 460 px. Read for narration: 2 a sheet at 620 px (final panel ids).
Zoom one page: 1 a sheet at 900. Grid labels are thousandths = box_1000 units.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLORS = ["#ff0040", "#00b050", "#0070ff", "#ff8c00", "#b000ff", "#00c0c0", "#ff00c0", "#808000"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def draw_page(chapter_dir: Path, page: dict, width: int) -> Image.Image:
    im = Image.open(chapter_dir / "pages" / page["page_filename"]).convert("RGB")
    scale = width / im.width
    im = im.resize((width, round(im.height * scale)), Image.LANCZOS)
    w, h = im.size
    d = ImageDraw.Draw(im, "RGBA")
    small = ImageFont.truetype(FONT, max(10, width // 60))
    big = ImageFont.truetype(FONT, max(16, width // 18))
    for g in range(100, 1000, 100):  # grid in thousandths
        x, y = g * w / 1000, g * h / 1000
        d.line([(x, 0), (x, h)], fill=(0, 160, 255, 70), width=1)
        d.line([(0, y), (w, y)], fill=(0, 160, 255, 70), width=1)
        d.text((x + 2, 1), str(g), fill=(0, 90, 200, 255), font=small)
        d.text((1, y + 1), str(g), fill=(0, 90, 200, 255), font=small)
    for i, panel in enumerate(page.get("panels", [])):
        y0, x0, y1, x1 = panel["box_1000"]
        box = (x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000)
        color = COLORS[i % len(COLORS)]
        d.rectangle(box, outline=color, width=max(3, width // 200))
        label = str(i + 1)
        tx, ty = box[0] + 6, box[1] + 6
        tb = d.textbbox((tx, ty), label, font=big)
        d.rectangle((tb[0] - 4, tb[1] - 2, tb[2] + 4, tb[3] + 2), fill=color)
        d.text((tx, ty), label, fill="white", font=big)
    return im


def main() -> None:
    chapter_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    per, width = int(sys.argv[3]), int(sys.argv[4])
    pages = json.loads((chapter_dir / "crops.json").read_text())["pages"]
    if len(sys.argv) > 5:
        a, b = map(int, sys.argv[5].split("-"))
        pages = [p for p in pages if a <= p["page_index"] <= b]
    out_dir.mkdir(parents=True, exist_ok=True)
    head = ImageFont.truetype(FONT, 22)
    for s in range(0, len(pages), per):
        group = pages[s:s + per]
        tiles = [draw_page(chapter_dir, p, width * (2 if Image.open(chapter_dir / "pages" / p["page_filename"]).width > 2000 else 1)) for p in group]
        H = max(t.height for t in tiles) + 30
        W = sum(t.width for t in tiles) + 10 * (len(tiles) - 1)
        sheet = Image.new("RGB", (W, H), "white")
        x = 0
        dd = ImageDraw.Draw(sheet)
        for p, t in zip(group, tiles):
            dd.text((x + 4, 2), f"{p['page_filename']}  idx {p['page_index']}  n={len(p.get('panels', []))}"
                    + ("" if p.get("is_story_page", True) else "  NOT STORY"), fill="black", font=head)
            sheet.paste(t, (x, 30))
            x += t.width + 10
        name = out_dir / f"sheet_{group[0]['page_index']:03d}-{group[-1]['page_index']:03d}.jpg"
        sheet.save(name, quality=85)
        print(name)


if __name__ == "__main__":
    main()
