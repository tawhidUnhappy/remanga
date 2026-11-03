"""The upload PDF - the first half of making a project's upload set (titles,
thumbnails, description) with an LLM, the way the narration and the crop are
made: the images it may use and the story go to the LLM with
prompts/upload.md, and its JSON reply, pasted into upload/upload_reply.txt,
is upload_reply.py's to use."""

from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc
from remanga.json_io import has_real_json_content
from remanga.narration import panel_files
from remanga.paths import PROMPTS_DIR, chapter_identity_fields, get_upload_dir, get_upload_pdf_dir
from remanga.pdf import build_image_pdf
from remanga.pdf.manifest_info import wrap_lines
from remanga.upload_plan import REPLY_NAME, candidates as offer
from remanga.upload_plan.facts import credits, story
from remanga.upload_plan.handoff import record_of, text_lines, write_record
from remanga.workflow.long_video import long_label, long_videos
from remanga.workflow.upload import chapter_fields

PROMPT_PATH = PROMPTS_DIR / "upload.md"
_WORKERS = min(8, os.cpu_count() or 1)


def upload_reply_path(project: str) -> Path:
    return get_upload_dir(project) / REPLY_NAME


def has_upload_reply(project: str) -> bool:
    return has_real_json_content(upload_reply_path(project))


@dataclass
class UploadPdfResult:
    parts: list[Path]
    prompt: Path
    reply: Path
    chapters: list[str]
    offered: int
    credits_known: bool
    story_from: str | None


def make_upload_pdf(project: str, chapters: list[str], config: RemangaConfig) -> UploadPdfResult:
    """The upload PDF of these chapters' panels - pdf/upload/upload_1.pdf, ... -
    and the record of what it offers. An empty upload_reply.txt is put in
    place to paste into."""
    chapters = [c for c in chapters if panel_files(project, c)]
    if not chapters:
        raise FileNotFoundError("None of these chapters has cut panels yet - the thumbnails are made of them. "
                                "Create the panels (or make the PDF) first.")
    made = long_videos(project)
    label = made[0]["label"] if made else long_label(project, chapters)
    found = credits(project, config)
    told = story(project, chapters)
    offered = offer.pick(project, chapters, told["not_story"])
    if not offered:
        raise FileNotFoundError("No panel in these chapters is big enough for a thumbnail.")
    record = record_of(project, chapters, label, chapter_fields(label)["num"], offered)
    identity = chapter_identity_fields(project, chapters[0])
    pdf_dir = get_upload_pdf_dir(project)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=pdf_dir, prefix=".upload-") as scratch, \
            ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        images = list(pool.map(lambda c: offer.prepared(c, Path(scratch)), offered))

        def text(full_ids: list[str], part_ids: list[str], index: int, total: int) -> list[str]:
            return wrap_lines(text_lines(identity, found, told, record, part_ids, index, total))

        parts = build_image_pdf(images, pdf_dir, config.pdf.max_mb, "upload", text, own_size=True, noun="images")
    write_record(pdf_dir, record)
    reply = upload_reply_path(project)
    reply.parent.mkdir(parents=True, exist_ok=True)
    if not reply.exists():
        reply.write_text("", encoding="utf-8")
    return UploadPdfResult(parts, PROMPT_PATH, reply, chapters, len(offered),
                           bool(found.get("story") or found.get("art")), told["memory_from"])


def print_upload_handoff(result: UploadPdfResult) -> None:
    console.print(f"[dim]{result.offered} images from chapter(s) {_esc(', '.join(result.chapters))}"
                  + (f"; the story so far from chapter {_esc(result.story_from)}'s narration" if result.story_from
                     else "; no narration yet - the LLM sees the images only") + ".[/]")
    if not result.credits_known:
        console.print("[yellow]Who made the manga is not known (its site does not say) - the description leaves "
                      "the credits out.[/]")
    console.print("\n[bold]Give these to the LLM[/]")
    console.print(f"  {display_path(result.prompt, wrap=False)}  [dim](the instructions)[/]")
    for part in result.parts:
        console.print(f"  {display_path(part, wrap=False)}")
    console.print("[bold]Paste its reply into[/]")
    console.print(f"  {display_path(result.reply, wrap=False)}")
    console.print("[dim]Then upload-from-reply (Use upload reply in a chapter's menu).[/]")
