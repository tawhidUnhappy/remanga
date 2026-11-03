"""The crop reply - the second half of cropping with an LLM (crop_pdf.py is
the first): the reply pasted into chapters/chapter_N/crop_reply.txt, read
against the crop PDF it answers, becomes the chapter's panel marks, and the
panels are cut. A reply that does not check out changes nothing and gets a
fix request to paste back into the same chat, as the narration's does."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.crop_plan import (
    FIX_REQUEST_NAME,
    CropReplyError,
    apply_edits,
    apply_page_lines,
    cut_report,
    page_record,
    read_reply,
)
from remanga.crop_plan.breakouts import still_cut
from remanga.crop_plan.handoff import read_record
from remanga.crop_plan.reply import fix_request_text, header_warnings, misplaced, shape_problems
from remanga.json_io import write_json
from remanga.paths import get_crops_path, get_pdf_dir
from remanga.workflow.crop_pdf import crop_reply_path, has_crop_reply
from remanga.workflow.panels import cut_panels


@dataclass
class CropReplyResult:
    changed: list[str]          # what the reply changed, a line per page or edit
    panels: int                 # panels cut
    warnings: list[str] = field(default_factory=list)
    report: list[str] = field(default_factory=list)     # cut panels that do not match their marks
    problems: list[str] = field(default_factory=list)   # the LLM's own `# problem` notes


def marks_from_reply(project: str, chapter: str, config: RemangaConfig) -> CropReplyResult:
    """The pasted crop reply, read against the crop PDF it answers, saved as
    the chapter's panel marks; then the panels are cut. A reply that does not
    check out changes nothing: CropReplyError, with the fix request written
    when the LLM is the one to fix it."""
    from remanga.store.locks import chapter_lock

    reply = crop_reply_path(project, chapter)
    if not has_crop_reply(project, chapter):
        raise FileNotFoundError(f"Chapter {chapter} has no crop reply yet - paste the LLM's reply into {reply}")
    pdf_dir = get_pdf_dir(project, chapter, create=False)
    record = read_record(pdf_dir)
    if not record:
        raise FileNotFoundError(f"Chapter {chapter} has no crop PDF to read the reply against - its numbers are "
                                f"the boxes drawn in it. Make the crop PDF and send it.")
    plan = read_reply(reply.read_text(encoding="utf-8"))
    wrong_place = misplaced(plan, chapter, record)
    if wrong_place:
        raise CropReplyError(wrong_place, [wrong_place])
    errors = plan.errors + shape_problems(plan, record)
    warnings = header_warnings(plan, chapter, record)
    strip = record["layout"] == "long_strip"
    if strip:
        save, changed = _strip_marks(project, chapter, record, plan, errors, warnings)
    else:
        outcome = apply_page_lines(record, page_record(project, chapter), plan.pages, src="llm", every_page=True)
        errors += outcome.errors
        warnings += outcome.warnings + _still_cut(record, outcome.record, plan)
        changed = outcome.changed

        def save() -> None:
            write_json(get_crops_path(project, chapter), outcome.record)

    fix = pdf_dir / FIX_REQUEST_NAME
    if errors:
        errors.sort(key=_line_of)
        fix.write_text(fix_request_text(chapter, errors, record["layout"]), encoding="utf-8")
        raise CropReplyError(f"Chapter {chapter}'s crop reply has {len(errors)} problem(s), so nothing was changed:\n"
                             + "\n".join(f"  - {e}" for e in errors)
                             + f"\nPaste {fix} into the same chat, then paste the new reply over {reply}.",
                             errors, fix)
    fix.unlink(missing_ok=True)
    with chapter_lock(project, chapter):
        save()
        panels = cut_panels(project, chapter, config, force=True)
    report = [] if strip else cut_report(project, chapter)
    return CropReplyResult(changed, len(panels), warnings, report, plan.problems)


def _line_of(error: str) -> int:
    """Which line, page or edit of the reply an error names (0: none) - the
    fix request lists them in reply order."""
    found = re.match(r"(?:line|page|edit|pages entry) (\d+)", error)
    return int(found.group(1)) if found else 0


def _still_cut(record: dict, after: dict, plan) -> list[str]:
    """The hints of the pages the reply named whose figure or bubble no panel
    now holds whole - fine when meant (a figure shown whole in a shot of its
    own elsewhere), worth a look when not."""
    named = {line.page for line in plan.pages}
    now = {p["page_index"]: [tuple(q["box_1000"]) for q in p.get("panels") or []] for p in after.get("pages", [])}
    return [f"page {page['page_index']}: {hint['label']} ({hint['why']}) is still cut by every panel"
            for page in record["pages"] if page["page_index"] in named and now.get(page["page_index"])
            for hint in page.get("hints") or [] if still_cut(hint, now[page["page_index"]])]


def _strip_marks(project: str, chapter: str, record: dict, plan, errors: list[str], warnings: list[str]):
    """A long strip's reply: its edits applied to the panels the PDF drew.
    Returns the saving step and what changed."""
    from remanga.plugins.long_strip.layout import source_pages
    from remanga.plugins.long_strip.marks import read_marks, sources_record, write_marks

    sources = source_pages(project, chapter)
    if sources_record(sources) != record["sources"]:
        raise CropReplyError(f"Chapter {chapter}'s downloaded pages changed since its crop PDF was made, so the "
                             f"reply's rows no longer fit them - make the crop PDF again and send it.", [])
    outcome = apply_edits([tuple(p) for p in record["panels"]], plan.edits, record["height"])
    errors += outcome.errors
    now = read_marks(project, chapter, sources)
    drawn = [tuple(p) for p in record["panels"]]
    if now is not None and sorted((m[0], m[1]) for m in now) not in (drawn, outcome.panels):
        warnings.append("the strip's marks were changed after the crop PDF was made - the reply replaced that change")

    def save() -> None:
        write_marks(project, chapter, sources, [list(p) for p in outcome.panels], record["height"])

    return save, outcome.changed


def print_reply_result(chapter: str, result: CropReplyResult) -> None:
    console.print(f"[bold green]✓ Chapter {_esc(chapter)}: panel marks saved from the crop reply - "
                  f"{len(result.changed)} change(s), {result.panels} panel(s) cut[/]")
    for line in result.changed:
        console.print(f"  {_esc(line)}")
    for line in result.problems:
        console.print(f"[yellow]  The LLM noted: {_esc(line)}[/]")
    for line in result.warnings + result.report:
        console.print(f"[yellow]  ! {_esc(line)}[/]")
    console.print("[dim]Look the marks over in the marker if you like (mark), then make the PDF.[/]")
