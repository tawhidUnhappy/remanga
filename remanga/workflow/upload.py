"""One YouTube title, description and thumbnail per project, stamped for each
video (user request, 2026-10-06).

    projects/<P>/upload/title.txt        the title; {num} is where the chapter
                                         goes - left out, " ({num})" is added
    projects/<P>/upload/description.txt  the description; {num} and {chapter}
    projects/<P>/upload/thumbnail.json   the thumbnail spec (video/thumbnail.py);
                                         its labels may hold {num} too

{num} is the chapter zero-padded - 01, 05.5, 01-02 for a long video - and
{chapter} spelled out - Chapter 1, Chapters 1-2.

Each finished video gets its own copy beside it, named like it:
<P>_ch<N>_{title.txt,description.txt,thumbnail.jpg}. Make video empties the
video folder, so the copies are written again after every render (make_video,
remix_video, join_chapters) - the templates in upload/ are never touched.
After editing them, `remanga upload -p <P>` restamps every video there is."""

from __future__ import annotations

import json
import re
from pathlib import Path

from remanga.console import console, escape as _esc
from remanga.paths import get_final_video_path, get_long_video_path, get_upload_dir

YOUTUBE_TITLE_LIMIT = 100
TITLE, DESCRIPTION, THUMBNAIL = "title.txt", "description.txt", "thumbnail.json"


def chapter_fields(label: str) -> dict[str, str]:
    """{num}: every chapter number zero-padded to two digits (1 -> 01,
    5.5 -> 05.5, 1-3+7 -> 01-03+07); {chapter}: Chapter 1 / Chapters 1-2."""
    # Only whole-number parts are padded: 5.5 -> 05.5, never 05.05.
    num = re.sub(r"(?<![.\d])\d+", lambda m: m.group().zfill(2), label)
    several = any(sep in label for sep in "-+")
    return {"num": num, "chapter": f"Chapter{'s' if several else ''} {label}"}


def _fill(template: str, fields: dict[str, str]) -> str:
    # str.replace, not format: a description may well hold braces of its own.
    for key, value in fields.items():
        template = template.replace("{" + key + "}", value)
    return template


def has_templates(project: str) -> bool:
    folder = get_upload_dir(project)
    return any((folder / name).exists() for name in (TITLE, DESCRIPTION, THUMBNAIL))


def stamp(project: str, label: str, video: Path) -> list[Path]:
    """Writes this video's title, description and thumbnail beside it from
    the project's templates - whichever of the three exist. Returns what it
    wrote."""
    folder = get_upload_dir(project)
    fields = chapter_fields(label)
    base = video.name.removesuffix("_recap.mp4")
    written: list[Path] = []

    title_file = folder / TITLE
    if title_file.exists():
        title = title_file.read_text(encoding="utf-8").strip()
        if "{num}" not in title:
            title += " ({num})"
        title = _fill(title, fields)
        if len(title) > YOUTUBE_TITLE_LIMIT:
            console.print(f"  [yellow]- the title is {len(title)} characters; YouTube cuts it at "
                          f"{YOUTUBE_TITLE_LIMIT}[/]")
        out = video.with_name(f"{base}_title.txt")
        out.write_text(title + "\n", encoding="utf-8")
        written.append(out)

    description_file = folder / DESCRIPTION
    if description_file.exists():
        out = video.with_name(f"{base}_description.txt")
        out.write_text(_fill(description_file.read_text(encoding="utf-8").strip(), fields) + "\n",
                       encoding="utf-8")
        written.append(out)

    spec_file = folder / THUMBNAIL
    if spec_file.exists():
        from remanga.video.thumbnail import compose

        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        spec.setdefault("project", project)
        out = video.with_name(f"{base}_thumbnail.jpg")
        compose(spec, fields=fields).save(out, quality=92)
        written.append(out)
    return written


def stamp_quietly(project: str, label: str, video: Path) -> None:
    """stamp() after a render: a broken template is reported, never allowed
    to fail the video it is for."""
    if not has_templates(project) or not video.exists():
        return
    try:
        written = stamp(project, label, video)
    except Exception as error:  # the video is done: say what went wrong and move on
        console.print(f"[yellow]Upload files not written ({_esc(str(error))}) - fix upload/ and run "
                      f"`remanga upload -p {_esc(project)}`[/]")
        return
    if written:
        console.print(f"[cyan]Upload files:[/] {', '.join(_esc(p.name) for p in written)}")


def stamp_all(project: str) -> list[Path]:
    """Every finished video of the project - each chapter's and each long
    one - stamped again from upload/. For after editing the templates."""
    from remanga.workflow.chapters import local_chapters
    from remanga.workflow.long_video import long_videos

    if not has_templates(project):
        raise FileNotFoundError(f"Nothing in {get_upload_dir(project)} yet - write {TITLE}, {DESCRIPTION} "
                                f"and/or {THUMBNAIL} there first.")
    written: list[Path] = []
    for chapter in local_chapters(project):
        video = get_final_video_path(project, chapter, create=False)
        if video.exists():
            written += stamp(project, chapter, video)
    for long in long_videos(project):
        if long["video"]:
            written += stamp(project, long["label"], get_long_video_path(project, long["label"], create=False))
    return written
