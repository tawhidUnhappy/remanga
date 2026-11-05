"""The upload reply - the second half of making the upload set with an LLM
(upload_pdf.py is the first): the reply pasted into upload/upload_reply.txt,
read against the upload PDF it answers, becomes the project's upload/
templates - title.txt, title_b.txt, title_c.txt, thumbnail.json, ... and the
one description.txt - with a preview of each thumbnail, and every finished
video is stamped again. What it replaces is kept in upload/old_<time>/. A
reply that does not check out changes nothing and gets a fix request."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.paths import get_upload_dir, get_upload_pdf_dir, load_project_metadata
from remanga.upload_plan import FIX_REQUEST_NAME, UploadReplyError, read_upload_reply
from remanga.upload_plan.description import description_text
from remanga.upload_plan.facts import credits
from remanga.upload_plan.framing import BADGE_TEXT, spec_for
from remanga.upload_plan.handoff import read_record
from remanga.upload_plan.reply import fix_request_text, misplaced
from remanga.workflow.upload import chapter_fields, stamp_all
from remanga.workflow.upload_pdf import has_upload_reply, upload_reply_path

# The templates a reply writes, and anything of theirs it would leave stale.
TEMPLATES = ("title.txt", "title_*.txt", "thumbnail.json", "thumbnail_*.json", "description.txt",
             "description_*.txt", "preview_*.jpg")


@dataclass
class UploadReplyResult:
    titles: dict[str, str]                  # letter -> title
    written: list[Path]
    previews: list[Path]
    stamped: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)   # the LLM's own notes
    kept: Path | None = None                # where what it replaced went


def upload_from_reply(project: str, config: RemangaConfig) -> UploadReplyResult:
    """The pasted upload reply, read against the upload PDF it answers, as the
    project's upload set; then every finished video stamped with it."""
    from remanga.video.thumbnail import compose

    reply = upload_reply_path(project)
    if not has_upload_reply(project):
        raise FileNotFoundError(f"No upload reply yet - paste the LLM's reply into {reply}")
    pdf_dir = get_upload_pdf_dir(project)
    record = read_record(pdf_dir)
    if not record:
        raise FileNotFoundError("There is no upload PDF to read the reply against - its images are the ones the "
                                "reply names. Make the upload PDF and send it.")
    plan = read_upload_reply(reply.read_text(encoding="utf-8"), record)
    wrong = misplaced(plan, record)
    if wrong:
        raise UploadReplyError(wrong, [wrong])
    fix = pdf_dir / FIX_REQUEST_NAME
    if plan.errors:
        fix.write_text(fix_request_text(plan.errors), encoding="utf-8")
        raise UploadReplyError(f"The upload reply has {len(plan.errors)} problem(s), so nothing was changed:\n"
                               + "\n".join(f"  - {e}" for e in plan.errors)
                               + f"\nPaste {fix} into the same chat, then paste the new reply over {reply}.",
                               plan.errors, fix)
    fix.unlink(missing_ok=True)

    found = credits(project, config)
    files: dict[str, str] = {}
    specs: dict[str, dict] = {}
    for variant in sorted(plan.variants, key=lambda v: v.letter):
        suffix = "" if variant.letter == "A" else f"_{variant.letter.lower()}"
        files[f"title{suffix}.txt"] = variant.title + "\n"
        specs[variant.letter] = spec_for(project, variant, record)
        if variant.badge and not any(lab.get("text") == BADGE_TEXT for lab in specs[variant.letter]["labels"]):
            plan.warnings.append(f"Set {variant.letter} has no chapter badge: no corner was free (a face or a label "
                                 f"holds the top corners and the bottom-left). Box a tile's subject tighter, around "
                                 f"the face, or swap the tiles, and use the reply again.")
        files[f"thumbnail{suffix}.json"] = json.dumps(specs[variant.letter], indent=1) + "\n"
    files["description.txt"] = description_text(plan.hook, plan.hashtags,
                                                load_project_metadata(project).get("manga_url", ""), found)

    folder = get_upload_dir(project)
    kept = _keep_old(folder, files)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    previews = []
    for letter, spec in specs.items():
        path = folder / f"preview_{letter.lower()}.jpg"
        compose(spec, fields=chapter_fields(record["label"])).save(path, quality=90)
        previews.append(path)
    try:
        stamped = stamp_all(project)
    except FileNotFoundError:
        stamped = []
    return UploadReplyResult({v.letter: v.title for v in plan.variants}, [folder / n for n in files], previews,
                             stamped, plan.warnings, plan.problems, kept)


def _keep_old(folder: Path, files: dict[str, str]) -> Path | None:
    """Moves the templates there now into upload/old_<time>/ - unless they are
    exactly what is about to be written (the same reply used again)."""
    old = sorted({p for pattern in TEMPLATES for p in folder.glob(pattern)})
    unchanged = {p.name for p in old if p.name in files and p.read_text(encoding="utf-8") == files[p.name]}
    if not old or (unchanged == set(files) and all(p.name in files or p.suffix == ".jpg" for p in old)):
        return None
    kept = folder / f"old_{time.strftime('%Y%m%d-%H%M%S')}"
    kept.mkdir(exist_ok=True)
    for path in old:
        shutil.move(str(path), kept / path.name)
    return kept


def print_upload_result(result: UploadReplyResult) -> None:
    console.print(f"[bold green]✓ Upload set written from the reply - {len(result.titles)} title/thumbnail "
                  f"pair(s) and the description[/]")
    for letter, title in result.titles.items():
        console.print(f"  {letter}: {_esc(title)}")
    for path in result.previews:
        console.print(f"  [dim]preview:[/] {_esc(str(path))}")
    if result.kept:
        console.print(f"[dim]What it replaced is kept in {_esc(str(result.kept))}[/]")
    for line in result.problems:
        console.print(f"[yellow]  The LLM noted: {_esc(line)}[/]")
    for line in result.warnings:
        console.print(f"[yellow]  ! {_esc(line)}[/]")
    console.print(f"[cyan]Stamped beside the videos:[/] {len(result.stamped)} file(s)" if result.stamped
                  else "[dim]No finished video yet - each is stamped as it is made.[/]")
