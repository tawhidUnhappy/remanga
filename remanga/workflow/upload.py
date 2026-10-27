"""One YouTube title, description and thumbnail per project, stamped for each
video (user request, 2026-10-06).

    projects/<P>/upload/title.txt        the title; {num} is where the chapter
                                         goes - left out, " ({num})" is added
    projects/<P>/upload/description.txt  the description; {num} and {chapter}
    projects/<P>/upload/thumbnail.json   the thumbnail spec (video/thumbnail.py);
                                         its labels may hold {num} too

{num} is the chapter zero-padded - 01, 05.5, 01-02 for a long video - and
{chapter} spelled out - Chapter 1, Chapters 1-2. {timestamps} is a long
video's chapter list for YouTube ("0:00 Chapter 1" a line); in a chapter's
own video it is empty, and the blank lines around it close up.

Each finished video gets its own copy beside it, named like it:
<P>_ch<N>_{title.txt,description.txt,thumbnail.jpg}. For A/B tests, more
titles and thumbnails sit beside them as title_b.txt, thumbnail_b.json, ...;
then each set gets a folder of its own beside the video instead - A/ (title.txt,
thumbnail.json), B/ (title_b.txt, thumbnail_b.json), ... - each holding its
title.txt and thumbnail.jpg, so a pair is never mixed up (user request,
2026-10-14), and the one description is written once beside the video as
<P>_ch<N>_description.txt (user request, 2026-10-27). Only description_b.txt,
... (user request, 2026-10-24) put a description in each set's folder - its
own, or description.txt for a set without one.
Make video empties the
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


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def timestamps(project: str, label: str, video: Path) -> str:
    """A long video's chapters as YouTube reads them: the first at 0:00 (the
    intro, when there is one in front), one line each. Empty for a chapter's
    own video."""
    from remanga.paths import get_long_videos_dir
    from remanga.workflow.long_video import chapter_starts

    if video.parent.parent != get_long_videos_dir(project):
        return ""
    starts = chapter_starts(project, label)
    if not starts:
        return ""
    lines = [] if min(starts.values()) < 1 else ["0:00 Intro"]
    lines += [f"{_clock(at)} Chapter {chapter}" for chapter, at in starts.items()]
    return "\n".join(lines)


def has_templates(project: str) -> bool:
    folder = get_upload_dir(project)
    return any((folder / name).exists() for name in (TITLE, DESCRIPTION, THUMBNAIL))


def stamp(project: str, label: str, video: Path) -> list[Path]:
    """Writes this video's title, description and thumbnail beside it from
    the project's templates - whichever exist; with A/B variants, one folder
    per letter, and the one description (when there is only description.txt)
    once beside the video rather than a copy in every folder. Returns what
    it wrote."""
    templates = get_upload_dir(project)
    fields = chapter_fields(label)
    base = video.name.removesuffix("_recap.mp4")
    titles = {_letter(p): p for p in _variants(templates, TITLE)}
    thumbnails = {_letter(p): p for p in _variants(templates, THUMBNAIL)}
    descriptions = {_letter(p): p for p in _variants(templates, DESCRIPTION)}
    letters = sorted(set(titles) | set(thumbnails) | set(descriptions)) or ["A"]

    stamp_fields = {**fields, "timestamps": timestamps(project, label, video)} if descriptions else fields
    # Test & Compare tests titles and thumbnails only, so variants usually
    # share one description: it is written once, beside the video (user
    # request, 2026-10-27 - three identical copies were noise).
    one_description = len(letters) > 1 and set(descriptions) == {"A"}

    _clear_stamps(video.parent, base)
    written: list[Path] = []
    for letter in letters:
        if len(letters) > 1:
            out = video.parent / letter
            out.mkdir(exist_ok=True)
            names = {"title": out / "title.txt", "description": out / "description.txt",
                     "thumbnail": out / "thumbnail.jpg"}
        else:
            names = {kind: video.with_name(f"{base}_{kind}.{'jpg' if kind == 'thumbnail' else 'txt'}")
                     for kind in ("title", "description", "thumbnail")}
        if letter in titles:
            title = titles[letter].read_text(encoding="utf-8").strip()
            if "{num}" not in title:
                title += " ({num})"
            title = _fill(title, fields)
            if len(title) > YOUTUBE_TITLE_LIMIT:
                console.print(f"  [yellow]- {titles[letter].name}: the title is {len(title)} characters; "
                              f"YouTube cuts it at {YOUTUBE_TITLE_LIMIT}[/]")
            names["title"].write_text(title + "\n", encoding="utf-8")
            written.append(names["title"])
        template = None if one_description else descriptions.get(letter) or descriptions.get("A")
        if template is not None:
            _write_description(template, stamp_fields, names["description"])
            written.append(names["description"])
        if letter in thumbnails:
            from remanga.video.thumbnail import compose

            spec = json.loads(thumbnails[letter].read_text(encoding="utf-8"))
            spec.setdefault("project", project)
            compose(spec, fields=fields).save(names["thumbnail"], quality=92)
            written.append(names["thumbnail"])
    if one_description:
        shared = video.with_name(f"{base}_description.txt")
        _write_description(descriptions["A"], stamp_fields, shared)
        written.append(shared)
    return written


def _write_description(template: Path, fields: dict[str, str], out: Path) -> None:
    text = _fill(template.read_text(encoding="utf-8").strip(), fields)
    out.write_text(re.sub(r"\n{3,}", "\n\n", text) + "\n", encoding="utf-8")


def _variants(folder: Path, name: str) -> list[Path]:
    """title.txt and its A/B variants title_b.txt, title_c.txt, ... - the
    plain one first."""
    stem, suffix = name.rsplit(".", 1)
    plain = folder / name
    return ([plain] if plain.exists() else []) + sorted(folder.glob(f"{stem}_*.{suffix}"))


def _letter(template: Path) -> str:
    """title.txt / thumbnail.json -> A, title_b.txt -> B."""
    return template.stem.partition("_")[2].upper() or "A"


STAMPED = ("title.txt", "description.txt", "thumbnail.jpg")


def _clear_stamps(folder: Path, base: str) -> None:
    """What an earlier stamp left beside this video - flat files or letter
    folders - so a set that went from three variants to one, or back, leaves
    nothing stale behind. Only those file names are ever removed, and a
    letter folder only once it is empty."""
    for old in [*folder.glob(f"{base}_title*.txt"), *folder.glob(f"{base}_thumbnail*.jpg"),
                *folder.glob(f"{base}_description.txt")]:
        old.unlink()
    for letter in folder.iterdir():
        if letter.is_dir() and len(letter.name) == 1 and letter.name.isupper():
            for name in STAMPED:
                (letter / name).unlink(missing_ok=True)
            if not any(letter.iterdir()):
                letter.rmdir()


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
