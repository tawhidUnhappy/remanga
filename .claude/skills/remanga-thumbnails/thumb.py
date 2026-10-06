"""Recap thumbnails (1280x720): the drawing lives in remanga/video/thumbnail.py
(also what stamps a project's upload/thumbnail.json onto every video); this is
the hand tool for designing a spec.

    python thumb.py sheet  PROJECT [CHAPTER]   contact sheets of every panel, named, to pick from
    python thumb.py grid   specs.json          render without labels, 10% grid drawn - read positions off it
    python thumb.py render specs.json          the thumbnail, saved beside the chapter's video

Run with remanga's .venv/bin/python from the repo root. A specs file maps keys
to specs (see specs.example.json; the format is in remanga/video/thumbnail.py).
For a project's own thumbnail, `grid`/`render` also take
projects/<P>/upload/thumbnail.json itself (one spec, no key)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from remanga.paths import get_final_video_path, get_panels_dir
from remanga.video.thumbnail import compose
from remanga.workflow.upload import chapter_fields

SCRATCH = Path("/tmp/remanga-thumbs")


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
    if len(sys.argv) < 3 or sys.argv[1] not in ("sheet", "grid", "render"):
        sys.exit(__doc__)
    mode = sys.argv[1]
    if mode == "sheet":
        sheets(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "1")
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
