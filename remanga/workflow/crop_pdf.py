"""The crop PDF - the first half of cropping with an LLM, the way the
narration is written with one. Every page goes to the LLM with the boxes the
machine found drawn on it, numbered, and the figures and bubbles that cross
them dashed (hints), with prompts/crop.md; its JSON reply, pasted into
chapters/chapter_N/crop_reply.txt, is crop_reply.py's to use. The reply is
in the format Claude crops in (remanga/crop_plan/), so both follow the same
rules."""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from remanga import plugins
from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc
from remanga.crop_plan import REPLY_NAME, page_record, strip_now
from remanga.crop_plan.found import read_found
from remanga.crop_plan.handoff import page_record_of, page_text, strip_record_of, strip_text, write_record
from remanga.crop_plan.sheets import draw_page, strip_sheets
from remanga.json_io import has_real_json_content
from remanga.languages import lettering as chapter_lettering
from remanga.layouts import layout_for
from remanga.narration import page_files
from remanga.paths import PROMPTS_DIR, chapter_identity_fields, get_chapter_dir, get_pages_dir, get_pdf_dir
from remanga.pdf import build_image_pdf
from remanga.pdf.manifest_info import wrap_lines
from remanga.workflow.chapters import has_marks
from remanga.workflow.projects import settle_reading_direction

PROMPT_PATH = PROMPTS_DIR / "crop.md"
PAGE_MAX_SIDE = 2000          # a page is drawn at its own size, shrunk to this at most
JPEG_QUALITY = 88
STRIP_ROWS, STRIP_WIDTH, STRIP_COLUMNS = 2000, 420, 3
_WORKERS = min(8, os.cpu_count() or 1)


def crop_reply_path(project: str, chapter: str) -> Path:
    return get_chapter_dir(project, chapter) / REPLY_NAME


def has_crop_reply(project: str, chapter: str) -> bool:
    return has_real_json_content(crop_reply_path(project, chapter))


@dataclass
class CropPdfResult:
    parts: list[Path]
    prompt: Path
    reply: Path
    found_by: str


def make_crop_pdf(project: str, chapter: str, config: RemangaConfig) -> CropPdfResult:
    """The chapter's crop PDF - pdf/chapter_N/crop_1.pdf, ... - and the record
    of the boxes it draws. A page manga with no marks yet is given MAGI's
    first (that is the proposal the LLM corrects); a long strip's are its
    saved marks or the gutter detector's. An empty crop_reply.txt is put in
    place to paste into."""
    if not page_files(project, chapter):
        raise FileNotFoundError(f"Chapter {chapter} has no pages - download it first.")
    settle_reading_direction(project)
    identity = dict(chapter_identity_fields(project, chapter))
    lettering = chapter_lettering(project, chapter, config.subtitles.language)
    if lettering:
        identity["lettering"] = lettering
    pdf_dir = get_pdf_dir(project, chapter)
    strip = layout_for(project, chapter).name == "long_strip"
    with tempfile.TemporaryDirectory(dir=pdf_dir, prefix=".crop-") as scratch:
        build = _strip_pdf if strip else _pages_pdf
        record, parts, found_by = build(project, chapter, identity, pdf_dir, Path(scratch), config)
    write_record(pdf_dir, record)
    reply = crop_reply_path(project, chapter)
    if not reply.exists():
        reply.write_text("", encoding="utf-8")
    return CropPdfResult(parts, PROMPT_PATH, reply, found_by)


def _pages_pdf(project: str, chapter: str, identity: dict, pdf_dir: Path, scratch: Path, config: RemangaConfig):
    found_by = _marks_for(project, chapter, config)
    record = page_record_of(chapter, page_record(project, chapter), _found_for(project, chapter, config))
    pages_dir = get_pages_dir(project, chapter)

    def drawn(page: dict) -> Path:
        with Image.open(pages_dir / page["page_filename"]) as image:
            sheet = draw_page(ImageOps.exif_transpose(image), [q["box_1000"] for q in page["panels"]],
                              stamp=f"page {page['page_index']}", max_side=PAGE_MAX_SIDE,
                              hints=page.get("hints", ()))
        path = scratch / f"page_{page['page_index']:03d}.jpg"
        sheet.save(path, quality=JPEG_QUALITY)
        return path

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        images = list(pool.map(drawn, record["pages"]))
    index_of = {path.stem: page["page_index"] for path, page in zip(images, record["pages"], strict=True)}

    def text(full_ids: list[str], part_ids: list[str], index: int, total: int) -> list[str]:
        return wrap_lines(page_text(identity, record, found_by, [index_of[s] for s in part_ids], index, total))

    parts = build_image_pdf(images, pdf_dir, config.pdf.max_mb, "crop", text, own_size=True, noun="pages")
    return record, parts, found_by


def _marks_for(project: str, chapter: str, config: RemangaConfig) -> str:
    """Makes sure the pages have the machine's boxes, and says whose they are."""
    if has_marks(project, chapter):
        sources = {q.get("src") for p in page_record(project, chapter)["pages"] for q in p.get("panels") or []}
        return ("found by MAGI v3 (a panel detector), numbered in its reading order" if sources <= {"ai"}
                else "as saved for the chapter - MAGI v3's, some fixed or drawn by hand")
    if not config.marker.magi_enabled:
        return "none drawn - the panel detector is off, so every panel needs a measured box"
    from remanga.paths import load_project_metadata
    from remanga.webui.detection import run_detection
    from remanga.webui.marker_session import MarkerSession

    console.print(f"[cyan]Chapter {_esc(chapter)} has no panel marks yet - MAGI v3 finds them first.[/]")
    session = MarkerSession(project, [chapter])
    state = session.state_for(chapter)
    run_detection(state, config.marker,
                  order_direction=load_project_metadata(project).get("reading_direction", "right_to_left"))
    if state.detect_error:
        raise RuntimeError(f"MAGI v3 could not find the panels ({state.detect_error}). The crop PDF is built on its "
                           f"boxes - if a video is rendering, MAGI is waiting for the GPU: make the crop PDF again "
                           f"when it is done.")
    session.save_chapter(chapter)
    return "found by MAGI v3 (a panel detector), numbered in its reading order"


def _found_for(project: str, chapter: str, config: RemangaConfig) -> dict[str, dict]:
    """What the detector saw on each page besides the panels - the figures and
    bubbles the hints come from. A chapter marked before MAGI kept them gets a
    pass of its own for them; if MAGI cannot run (the GPU busy rendering), the
    crop PDF is made without hints."""
    found = read_found(project, chapter)
    missing = [p for p in page_files(project, chapter) if p.name not in found]
    if not missing or not config.marker.magi_enabled:
        return found
    console.print(f"[cyan]Chapter {_esc(chapter)}: MAGI v3 looks for figures and bubbles that cross the boxes "
                  f"({len(missing)} page(s)).[/]")
    try:
        layout = layout_for(project, chapter)
        plugins.call(layout.detect, get_pages_dir(project, chapter), missing, config.marker, None)
    except Exception as error:   # hints help; the boxes alone still make a crop PDF
        console.print(f"[yellow]No hints this time - MAGI v3 could not run ({_esc(str(error))}).[/]")
    return read_found(project, chapter)


def _strip_pdf(project: str, chapter: str, identity: dict, pdf_dir: Path, scratch: Path, config: RemangaConfig):
    now = strip_now(project, chapter)
    found_by = "as saved for the chapter" if now.saved else "found by the strip's gutter detector"
    record = strip_record_of(chapter, now)
    images = []
    for number, sheet in enumerate(strip_sheets(now.view, now.panels, rows=STRIP_ROWS, width=STRIP_WIDTH,
                                                per_sheet=STRIP_COLUMNS, title=f"chapter {chapter}: "), start=1):
        path = scratch / f"strip_{number:03d}.jpg"
        sheet.save(path, quality=JPEG_QUALITY)
        images.append(path)

    def text(full_ids: list[str], part_ids: list[str], index: int, total: int) -> list[str]:
        return wrap_lines(strip_text(identity, record, now, found_by, index, total))

    parts = build_image_pdf(images, pdf_dir, config.pdf.max_mb, "crop", text, own_size=True, noun="sheets")
    return record, parts, found_by


def print_crop_handoff(result: CropPdfResult) -> None:
    console.print(f"[dim]Boxes: {_esc(result.found_by)}.[/]")
    console.print("\n[bold]Give these to the LLM[/]")
    console.print(f"  {display_path(result.prompt, wrap=False)}  [dim](the instructions)[/]")
    for part in result.parts:
        console.print(f"  {display_path(part, wrap=False)}")
    console.print("[bold]Paste its reply into[/]")
    console.print(f"  {display_path(result.reply, wrap=False)}")
    console.print("[dim]Then marks-from-reply (Use crop reply in the chapter's menu).[/]")


