"""Recap thumbnails (1280x720): the drawing lives in remanga/video/thumbnail.py
(also what stamps a project's upload/thumbnail.json onto every video); this is
the hand tool for designing a spec.

    python thumb.py sheet   PROJECT [CHAPTER]  contact sheets of every panel, named, to pick from
    python thumb.py offered PROJECT            contact sheets of the images the upload PDF offered, by id
    python thumb.py boxes   PROJECT ID [ID..]  those images with a 0-1000 grid - read an upload reply's
                                               subject and avoid boxes ([ymin, xmin, ymax, xmax]) off it
    python thumb.py grid    specs.json         render without labels, 10% grid drawn - read positions off it
    python thumb.py render  specs.json         the thumbnail, saved beside the chapter's video

Run with remanga's .venv/bin/python from the repo root. A specs file maps keys
to specs (see specs.example.json; the format is in remanga/video/thumbnail.py).
For a project's own thumbnail, `grid`/`render` also take
projects/<P>/upload/thumbnail.json itself (one spec, no key)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from remanga.paths import get_final_video_path, get_pages_dir, get_panels_dir, get_upload_pdf_dir
from remanga.upload_plan.handoff import read_record
from remanga.video.thumbnail import compose
from remanga.workflow.upload import chapter_fields

SCRATCH = Path("/tmp/remanga-thumbs")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def offered_images(project: str) -> dict[str, dict]:
    """The upload PDF's record of what it offered: id -> {kind, chapter, file, size, colour}."""
    record = read_record(get_upload_pdf_dir(project))
    if not record:
        sys.exit(f"No upload PDF for {project} yet - run ./run.sh upload-pdf -p {project} first.")
    return record["candidates"]


def offered_path(project: str, info: dict) -> Path:
    if info["kind"] == "page":
        return get_pages_dir(project, info["chapter"]) / info["file"]
    return get_panels_dir(project, info["chapter"], create=False) / info["file"]


def offered_sheets(project: str) -> None:
    """Every image the upload PDF offered, 40 to a sheet, each with its id and size (C = colour)."""
    offered = list(offered_images(project).items())
    cols, cell = 8, 300
    font = ImageFont.truetype(FONT, 16)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(offered), 40):
        chunk = offered[start:start + 40]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (cell + 6), rows * (cell + 26)), (40, 40, 40))
        draw = ImageDraw.Draw(sheet)
        for i, (cid, info) in enumerate(chunk):
            im = Image.open(offered_path(project, info)).convert("RGB")
            im.thumbnail((cell, cell))
            x, y = (i % cols) * (cell + 6), (i // cols) * (cell + 26)
            sheet.paste(im, (x + (cell - im.width) // 2, y + 22 + (cell - im.height) // 2))
            draw.text((x + 2, y + 2), f"{cid} {info['size'][0]}x{info['size'][1]}" + (" C" if info["colour"] else ""),
                      fill=(255, 230, 0), font=font)
        out = SCRATCH / f"offered_{project}_{start // 40:02d}.jpg"
        sheet.save(out, quality=85)
        print(out)


def boxes_sheet(project: str, ids: list[str], height: int = 820) -> None:
    """The images side by side, a line every 100 thousandths labelled on both axes - the grid an
    upload reply's boxes are measured in ([ymin, xmin, ymax, xmax], 0-1000 of the image)."""
    offered = offered_images(project)
    unknown = [i for i in ids if i not in offered]
    if unknown:
        sys.exit(f"Not offered by the upload PDF: {', '.join(unknown)}")
    font = ImageFont.truetype(FONT, 15)
    tiles = []
    for cid in ids:
        im = Image.open(offered_path(project, offered[cid])).convert("RGB")
        im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
        draw = ImageDraw.Draw(im, "RGBA")
        for g in range(100, 1000, 100):
            x, y = g * im.width / 1000, g * im.height / 1000
            draw.line([(x, 0), (x, im.height)], fill=(0, 200, 255, 130), width=1)
            draw.line([(0, y), (im.width, y)], fill=(0, 200, 255, 130), width=1)
            draw.text((x + 2, 2), str(g), fill=(255, 0, 80), font=font)
            draw.text((2, y + 2), str(g), fill=(255, 0, 80), font=font)
        tiles.append((cid, im))
    sheet = Image.new("RGB", (sum(t.width for _, t in tiles) + 12 * (len(tiles) + 1), height + 30), (30, 30, 30))
    x = 12
    for cid, im in tiles:
        sheet.paste(im, (x, 28))
        ImageDraw.Draw(sheet).text((x, 6), cid, fill=(255, 230, 0), font=font)
        x += im.width + 12
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out = SCRATCH / f"boxes_{project}_{'_'.join(ids)[:80]}.jpg"
    sheet.save(out, quality=88)
    print(out)


def sheets(project: str, chapter: str) -> None:
    """Every panel of the chapter, 60 to a sheet, each named - to pick from."""
    files = sorted(get_panels_dir(project, chapter, create=False).glob("*.png"))
    cols, cw, ch = 10, 240, 300
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(files), 60):
        chunk = files[start:start + 60]
        sheet = Image.new("RGB", (cols * cw, ((len(chunk) + cols - 1) // cols) * ch), "white")
        draw = ImageDraw.Draw(sheet)
        for i, f in enumerate(chunk):
            im = Image.open(f).convert("RGB")
            im.thumbnail((cw - 6, ch - 24))
            x, y = (i % cols) * cw, (i // cols) * ch
            sheet.paste(im, (x + 3, y + 20))
            draw.text((x + 4, y + 3), f.stem, fill="red")
        out = SCRATCH / f"sheet_{project}_{chapter}_{start // 60}.jpg"
        sheet.save(out, quality=80)
        print(out)


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("sheet", "offered", "boxes", "grid", "render"):
        sys.exit(__doc__)
    mode = sys.argv[1]
    if mode == "sheet":
        sheets(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "1")
        return
    if mode == "offered":
        offered_sheets(sys.argv[2])
        return
    if mode == "boxes":
        if len(sys.argv) < 4:
            sys.exit(__doc__)
        boxes_sheet(sys.argv[2], sys.argv[3:])
        return
    specs = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    if "tiles" in specs:  # one spec, e.g. projects/<P>/upload/thumbnail.json
        specs = {specs["project"]: specs}
    for key, spec in specs.items():
        chapter = str(spec.get("chapter", "1"))
        if mode == "grid":
            SCRATCH.mkdir(parents=True, exist_ok=True)
            out = SCRATCH / f"{key}_grid.jpg"
        else:
            video = get_final_video_path(spec["project"], chapter)
            out = video.with_name(video.name.removesuffix("_recap.mp4") + "_thumbnail.jpg")
        compose(spec, grid=mode == "grid", fields=chapter_fields(chapter)).save(out, quality=92)
        print(out)


if __name__ == "__main__":
    main()
