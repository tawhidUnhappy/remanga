"""Checking the LLM's page narration and turning it into panels/ and
narration.json.

The reply (prompts/page_narration.md <output_format>) has one entry per page:
a story page lists its `panels` - one short note per panel, in reading order -
and its `text`, the narration that covers every one of them; a page that isn't
story is skipped with a reason. Errors block the import and produce a fix
request to paste back into the same conversation, like the LLM crop reply.
Warnings never block.

Importing makes the page mode look to every later stage exactly like a
cropped chapter: each story page is copied into panels/ as that page's one
panel (`001_014` -> `001_014_01`), and narration.json gets one entry per such
panel. TTS, mix, render, review, verify and the panels-vs-narration gate then
work unchanged."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from remanga.console import console
from remanga.cropper.crop_report import write_manifest
from remanga.extensions.page_narration.paths import (
    FIX_REQUEST_NAME,
    chapter_page_files,
    get_page_upload_dir,
    get_reply_path,
    page_panel_id,
)
from remanga.json_io import has_real_json_content, json_from_reply, write_json
from remanga.narration.document import narration_document, narration_path
from remanga.paths import get_chapter_dir

SKIP_REASONS = ("credits", "ad", "blank", "duplicate")
PAGE_KEYS = ("page", "story", "skip", "panels", "text")
# Fewer words than this per panel listed usually means panels were summed up
# rather than each narrated.
MIN_WORDS_PER_PANEL = 12
# Image types every later stage reads as a panel as they are (video compose
# takes .png and .jpg); anything else is converted to PNG on import.
KEPT_SUFFIXES = (".png", ".jpg")

_CONTRACTION = re.compile(r"\b\w+(?:n't|'re|'ve|'ll|'d|'m)\b|\b(?:it|that|there|what|he|she|who|here)'s\b",
                          re.IGNORECASE)


@dataclass
class PageCheck:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImportOutcome:
    """`imported`, `invalid` (fix request written), `declined` (existing
    panels or narration kept) or `empty` (nothing pasted yet)."""

    state: str
    check: PageCheck | None = None
    fix_path: Path | None = None


def _style_warnings(stem: str, text: str) -> list[str]:
    """prompts/narration.md's voice rules that a program can see."""
    found = []
    if re.search(r"[\"“”]", text):
        found.append("quotation marks")
    if "?" in text or "!" in text:
        found.append("a question or exclamation mark")
    if "..." in text or "…" in text:
        found.append("an ellipsis")
    contractions = sorted({m.group(0) for m in _CONTRACTION.finditer(text)})
    if contractions:
        found.append(f"contractions ({', '.join(contractions[:4])})")
    return [f"{stem}: the narration uses {', '.join(found)} - the voice rules forbid them"] if found else []


def check_reply(doc: Any, page_stems: list[str], chapter_num: str) -> PageCheck:
    check = PageCheck()
    if not isinstance(doc, dict) or not isinstance(doc.get("pages"), list):
        check.errors.append('the reply is not a JSON object with a "pages" list')
        return check
    if "chapter" in doc and str(doc["chapter"]).strip().lstrip("0") != str(chapter_num).strip().lstrip("0"):
        check.warnings.append(f"the reply says chapter {doc['chapter']!r}, but it was pasted into "
                              f"chapter {chapter_num}")
    check.warnings.extend(f"the LLM reported: {problem}" for problem in doc.get("problems") or [])

    known, seen, story_pages = set(page_stems), [], 0
    for entry in doc["pages"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("page"), str):
            check.errors.append(f"an entry in pages has no page ID: {json.dumps(entry)[:80]}")
            continue
        stem = entry["page"]
        if stem not in known:
            check.errors.append(f"page {stem} is not one of this chapter's pages")
            continue
        if stem in seen:
            check.errors.append(f"page {stem} appears more than once")
            continue
        seen.append(stem)
        story, panels, text = entry.get("story"), entry.get("panels"), entry.get("text")
        if not isinstance(story, bool):
            check.errors.append(f'{stem}: "story" must be true or false')
            continue
        if not story:
            if entry.get("skip") not in SKIP_REASONS:
                check.errors.append(f"{stem}: a page that is not part of the story needs a skip of "
                                    f"{', '.join(SKIP_REASONS)} (got {entry.get('skip')!r})")
            if text:
                check.errors.append(f"{stem}: a skipped page has no narration - its text must be empty")
            continue
        story_pages += 1
        if not isinstance(panels, list) or not panels or not all(isinstance(p, str) and p.strip() for p in panels):
            check.errors.append(f'{stem}: "panels" must list every panel on the page, one short note each, '
                                f"in reading order")
            panels = None
        if not isinstance(text, str) or not text.strip():
            check.errors.append(f"{stem}: a story page needs its narration in text")
            continue
        if panels and len(text.split()) < MIN_WORDS_PER_PANEL * len(panels):
            check.warnings.append(f"{stem}: {len(text.split())} words for {len(panels)} panels - is every panel "
                                  f"narrated, with all of its dialogue")
        check.warnings.extend(_style_warnings(stem, text))
        unknown = sorted(set(entry) - set(PAGE_KEYS))
        if unknown:
            check.warnings.append(f"{stem}: ignored unknown key(s) {', '.join(unknown)}")

    missing = [stem for stem in page_stems if stem not in seen]
    if missing:
        check.errors.append(f"page(s) missing from pages: {', '.join(missing)}")
    elif seen != page_stems:
        check.warnings.append("pages are not in page order - they are put back in order on import")
    if not missing and not story_pages:
        check.errors.append("every page is marked as not part of the story - there is nothing to narrate")
    return check


def fix_request_text(chapter_num: str, errors: list[str]) -> str:
    """What to paste back into the same conversation (prompts/page_narration.md <follow_ups>)."""
    lines = [
        f"The page narration for chapter {chapter_num} didn't pass the pipeline's checks. Fix only the problems "
        f"below, checked against the page images, and reply with the complete page_narration.json again, in the "
        f"same format - every page, not only the ones that changed. Do not send memory.json again.",
        "",
        *[f"- {error}" for error in errors],
    ]
    return "\n".join(lines) + "\n"


def _existing_work(project_name: str, chapter_num: str) -> str | None:
    panels_dir = get_chapter_dir(project_name, chapter_num) / "panels"
    has_panels = panels_dir.exists() and any(p.is_file() for p in panels_dir.iterdir())
    has_narration = has_real_json_content(narration_path(project_name, chapter_num))
    if has_panels and has_narration:
        return "cropped panels and a narration.json"
    if has_panels:
        return "cropped panels"
    if has_narration:
        return "a narration.json"
    return None


def _write_page_panels(project_name: str, chapter_num: str, pages: list[Path]) -> list[Path]:
    """Each story page into panels/ as its one panel, after emptying panels/
    the way a fresh crop does."""
    panels_dir = get_chapter_dir(project_name, chapter_num) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    for old in panels_dir.iterdir():
        if old.is_file():
            with contextlib.suppress(OSError):
                old.unlink()
    written = []
    for page in pages:
        stem = page_panel_id(page.stem)
        if page.suffix.lower() in KEPT_SUFFIXES:
            out = panels_dir / f"{stem}{page.suffix.lower()}"
            shutil.copyfile(page, out)
        else:
            out = panels_dir / f"{stem}.png"
            with Image.open(page) as img:
                img.convert("RGB").save(out, "PNG")
        written.append(out)
    return written


def import_page_narration(project_name: str, chapter_num: str, *, replace: bool | None = None) -> ImportOutcome:
    """Checks the pasted reply and, when it passes, writes panels/ and
    narration.json from it. `replace` answers whether existing panels or
    narration may be replaced: None asks in a real terminal and keeps them
    anywhere else."""
    reply = get_reply_path(project_name, chapter_num)
    if not has_real_json_content(reply):
        return ImportOutcome("empty")
    page_files = chapter_page_files(project_name, chapter_num)
    stems = [page.stem for page in page_files]

    fix_path = get_page_upload_dir(project_name, chapter_num) / FIX_REQUEST_NAME
    try:
        doc = json_from_reply(reply.read_text(encoding="utf-8"))
        check = check_reply(doc, stems, chapter_num)
    except json.JSONDecodeError as error:
        check = PageCheck(errors=[f"the reply is not valid JSON ({error.msg} at line {error.lineno}, "
                                  f"column {error.colno})"])
    if check.errors:
        fix_path.write_text(fix_request_text(chapter_num, check.errors), encoding="utf-8")
        console.print(f"[bold red]✗ Chapter {chapter_num}: the page narration has {len(check.errors)} problem(s)[/]")
        for error in check.errors:
            console.print(f"  [red]- {error}[/]")
        return ImportOutcome("invalid", check=check, fix_path=fix_path)
    fix_path.unlink(missing_ok=True)

    existing = _existing_work(project_name, chapter_num)
    if existing:
        if replace is None:
            from remanga.tui import confirm, is_interactive

            replace = is_interactive() and confirm(
                f"Chapter {chapter_num} already has {existing} - replace them with the page narration?",
                default=False, note="panels/ becomes one image per story page, and narration.json is rewritten",
            ) is True
        if not replace:
            console.print(f"[yellow]Kept chapter {chapter_num}'s {existing}[/] "
                          f"[dim](pass --force to replace them with the page narration)[/]")
            return ImportOutcome("declined", check=check)

    entries = {entry["page"]: entry for entry in doc["pages"]}
    story = [page for page in page_files if entries[page.stem]["story"]]
    panel_paths = _write_page_panels(project_name, chapter_num, story)
    write_manifest(project_name, chapter_num, panel_paths)
    write_json(narration_path(project_name, chapter_num), narration_document(
        chapter_num, [(page_panel_id(page.stem), entries[page.stem]["text"].strip()) for page in story]))

    skipped = [f"{page.stem} ({entries[page.stem]['skip']})" for page in page_files if not entries[page.stem]["story"]]
    console.print(
        f"[bold green]✓ Chapter {chapter_num}: {len(story)} page(s) narrated[/] "
        f"[dim]- panels/ holds one image per story page, narration.json one entry per page"
        + (f"; skipped {', '.join(skipped)}" if skipped else "") + "[/]"
    )
    if check.warnings:
        console.print(f"[yellow]{len(check.warnings)} thing(s) worth a look:[/]")
        for warning in check.warnings:
            console.print(f"  [yellow]- {warning}[/]")
    return ImportOutcome("imported", check=check)
