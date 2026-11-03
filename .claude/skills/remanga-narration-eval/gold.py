"""A first draft of a chapter's gold transcript - every bubble, caption and sign of every panel, in
reading order - from MAGI v3's OCR of its pages (magi_ocr.py), to be checked against the pages and
corrected by eye before anything is scored with it.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-narration-eval/gold.py PROJECT CHAPTER OCR.json OUT.txt

One line per text, grouped under its page:

    ## 002_004
    002_004_01 | Catherine | speech | I'm your client, Catherine Moliniere.
    002_004_02 | ? | speech | It's an honor to meet you.

panel | speaker | kind | text. A text goes to the panel whose box holds its centre (crops.json); one in no
box goes to the nearest panel on its page, with `?outside` after its kind. The speaker is left `?` for the
checker to name (a name the story gives, or a description); kind is `speech`, or `sfx` where MAGI calls the
text not essential - the checker sets `thought`, `caption`, `sign` and `sfx` from the art. Hyphenated
line breaks are joined ("match- es" -> "matches"). score.py reads the corrected file."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from remanga.cropper.naming import panel_stem
from remanga.json_io import read_json_or
from remanga.paths import get_chapter_dir


def join_breaks(text: str) -> str:
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def panel_for(centre: tuple[float, float], boxes: list[tuple[str, tuple[float, float, float, float]]]):
    """(panel id, inside) - the box holding the point, else the nearest box."""
    x, y = centre
    for stem, (x0, y0, x1, y1) in boxes:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return stem, True

    def distance(b):
        return max(b[0] - x, 0, x - b[2]) ** 2 + max(b[1] - y, 0, y - b[3]) ** 2
    return min(boxes, key=lambda item: distance(item[1]))[0], False


def main() -> None:
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    project, chapter, ocr_path, out = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
    ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    crops = read_json_or(get_chapter_dir(project, chapter) / "crops.json", {}) or {}
    lines = []
    for page in crops.get("pages") or []:
        seen = ocr.get(page["page_filename"])
        lines.append(f"## {Path(page['page_filename']).stem}")
        if not seen or not page.get("panels"):
            continue
        w, h = seen["size"]
        boxes = [(panel_stem(chapter, page["page_index"], p["panel_id"]),
                  (p["box_1000"][1] * w / 1000, p["box_1000"][0] * h / 1000,
                   p["box_1000"][3] * w / 1000, p["box_1000"][2] * h / 1000)) for p in page["panels"]]
        order = {stem: i for i, (stem, _) in enumerate(boxes)}
        texts = seen.get("texts") or []
        essential = seen.get("essential") or []
        rows = []
        for n, item in enumerate(seen.get("ocr") or []):
            x0, y0, x1, y1 = item["box"]
            stem, inside = panel_for(((x0 + x1) / 2, (y0 + y1) / 2), boxes)
            # MAGI's essential flag belongs to its detected text boxes: the one this OCR box overlaps most.
            overlap = [max(0, min(x1, t[2]) - max(x0, t[0])) * max(0, min(y1, t[3]) - max(y0, t[1])) for t in texts]
            best = max(range(len(texts)), key=overlap.__getitem__) if texts and max(overlap) > 0 else None
            sfx = best is not None and best < len(essential) and not essential[best]
            kind = ("sfx" if sfx else "speech") + ("" if inside else " ?outside")
            rows.append((order[stem], n, f"{stem} | ? | {kind} | {join_breaks(item['text'])}"))
        lines += [row for *_, row in sorted(rows)]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    texts = sum(1 for line in lines if not line.startswith("##"))
    print(f"{out}: {texts} texts on {len(crops.get('pages') or [])} pages")


if __name__ == "__main__":
    main()
