"""After the panels are cut: the pages whose cut panels do not match their marks.

A mark can look right and still come out wrong - the gutter snapper eats a
caption at the page edge, or grows a panel into the blurb under it, and the
cutter drops a box it takes for a duplicate of another. None of that shows on
the marks; it shows here, as a panel cut much smaller or larger than marked,
or a page with fewer panels than marks."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from remanga.crop_plan.pages import page_boxes, page_record
from remanga.narration import panel_files
from remanga.paths import get_pages_dir

SIZE_RANGE = (0.7, 1.5)   # cut area / marked area outside this is reported


def cut_report(project: str, chapter: str) -> list[str]:
    """A line per page or panel worth a look, in page order."""
    cuts: dict[int, list[Path]] = {}
    for path in panel_files(project, chapter):
        cuts.setdefault(int(path.stem.rsplit("_", 2)[1]), []).append(path)
    found = []
    for page in page_record(project, chapter)["pages"]:
        marks, files = page_boxes(page), cuts.get(page["page_index"], [])
        if marks and len(marks) != len(files):
            found.append(f"page {page['page_index']}: {len(marks)} marked, {len(files)} cut - the cutter took "
                         f"one for a duplicate of another (boxes nearly the same)")
            continue
        if not marks:
            continue
        with Image.open(get_pages_dir(project, chapter) / page["page_filename"]) as image:
            width, height = image.size
        for (y0, x0, y1, x1), path in zip(marks, files, strict=True):
            mark_w, mark_h = (x1 - x0) * width / 1000, (y1 - y0) * height / 1000
            with Image.open(path) as image:
                cut_w, cut_h = image.size
            area = cut_w * cut_h / max(1.0, mark_w * mark_h)
            if not SIZE_RANGE[0] <= area <= SIZE_RANGE[1]:
                found.append(f"{path.stem}: marked {mark_w:.0f}x{mark_h:.0f}, cut {cut_w}x{cut_h} "
                             f"(area x{area:.2f}) - the gutter snapper moved it; if it is wrong, make the page exact")
    return found
