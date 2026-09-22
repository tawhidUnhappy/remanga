"""The chapter's panels as PDF parts for the LLM, and what to do with them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from remanga.chapters import chapter_sort_key
from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc
from remanga.json_io import read_json
from remanga.narration import PROMPT_PATH, panel_files, story_so_far
from remanga.paths import chapter_identity_fields, get_crops_path, get_narration_path, get_pages_dir, get_pdf_dir
from remanga.pdf import build_chapter_pdf, build_marked_pages
from remanga.pdf.manifest_info import MEMORY_KEY, MEMORY_SOURCE_KEY
from remanga.workflow.chapters import local_chapters
from remanga.workflow.panels import cut_panels
from remanga.workflow.projects import settle_reading_direction


@dataclass
class PdfResult:
    parts: list[Path]
    prompt: Path
    narration: Path
    story_from: str | None
    missing_before: list[str]

    def warnings(self) -> list[str]:
        if not self.missing_before:
            return []
        return [f"Chapter(s) {', '.join(self.missing_before)} before this one have no narration yet - the story "
                f"so far in this PDF " + (f"stops at chapter {self.story_from}." if self.story_from else "is empty.")]


def make_pdf(project: str, chapter: str, config: RemangaConfig) -> PdfResult:
    """The chapter as PDF parts: every page with its panel marks drawn on it,
    each followed by the panels cut from that page, with the chapter's
    identity and the story so far on each part's first page. The panels are
    cut first if the marks are newer than them. The story so far comes from
    the previous chapter's pasted narration. An empty narration.json is put in
    place to paste into."""
    panels = cut_panels(project, chapter, config) or panel_files(project, chapter)
    if not panels:
        raise FileNotFoundError(f"Chapter {chapter} has no panels - mark them in the Panel Marker first.")
    settle_reading_direction(project)

    info = dict(chapter_identity_fields(project, chapter))
    # The story so far: the memory section of the nearest earlier chapter's
    # pasted narration - only ever an earlier chapter's, so re-making a PDF
    # never hands the LLM what happens later.
    memory, source = story_so_far(project, chapter)
    if memory:
        info[MEMORY_KEY] = memory
        info[MEMORY_SOURCE_KEY] = source
    missing = [c for c in local_chapters(project)
               if chapter_sort_key(c) < chapter_sort_key(str(chapter))
               and (source is None or chapter_sort_key(c) > chapter_sort_key(source))]
    out_dir = get_pdf_dir(project, chapter)
    # The pages go in beside the panels so the LLM can see the layout each
    # panel was cut from (see pdf/marked_pages.py). They are drawn from the
    # same crops.json the panels were cut from, into a folder beside the PDF.
    marked = build_marked_pages(read_json(get_crops_path(project, chapter)),
                                get_pages_dir(project, chapter), out_dir / "pages", chapter)
    parts = build_chapter_pdf(marked, panels, out_dir, config.pdf.max_mb, info)

    narration = get_narration_path(project, chapter)
    if not narration.exists():
        narration.write_text("", encoding="utf-8")
    return PdfResult(parts, PROMPT_PATH, narration, source, missing)


def print_handoff(result: PdfResult) -> None:
    for warning in result.warnings():
        console.print(f"[yellow]{_esc(warning)}[/]")
    console.print("\n[bold]Give these to the LLM[/]")
    console.print(f"  {display_path(result.prompt, wrap=False)}  [dim](the instructions)[/]")
    for part in result.parts:
        console.print(f"  {display_path(part, wrap=False)}")
    console.print("[bold]Paste its reply into[/]")
    console.print(f"  {display_path(result.narration, wrap=False)}")
    console.print("[dim]Then make the video.[/]")
