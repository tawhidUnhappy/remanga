"""The chapter information on a PDF's leading text page: identity, which
panels this part holds (`contents`) and every panel of the chapter
(`full_manifest`), so a missing part is visible just by comparing the two."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_part_info(
    identity: dict[str, Any],
    full_ids: Sequence[str],
    part_ids: Sequence[str],
    part_index: int,
    total_parts: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One part's chapter_info.json payload - `identity` is
    remanga.paths.chapter_identity_fields' project/manga/chapter dict,
    `full_ids` is every item name in this format across every part, in
    order, and `part_ids` is just the ones actually in this part. `extra` is
    whatever a format adds for its reader (the grid formats' grouping, grid
    spec and page areas), placed right after the identity."""
    info = dict(identity)
    info.update(extra or {})
    info["part_index"] = part_index
    info["total_parts"] = total_parts
    info["total_items"] = len(full_ids)
    info["contents"] = list(part_ids)
    info["full_manifest"] = list(full_ids)
    return info


# Characters per line on the text page (11pt Helvetica across textpage.py's
# TEXT_PAGE_SIZE, inside 54pt margins, holds about this many).
LINE_WIDTH = 180
MEMORY_KEY = "story_so_far"
MEMORY_SOURCE_KEY = "story_so_far_from_chapter"
# The threads still open before this chapter, given in the skeleton's memory.
THREADS_KEY = "open_threads"


def info_to_text_lines(info: dict[str, Any]) -> list[str]:
    """A build_part_info() dict as plain lines for the PDF's text page(s),
    wrapped to the page. The page lists get labeled sections of their own,
    and on part 1 the story so far (MEMORY_KEY: lines from story.py, or an
    older caller's memory as indented JSON) and the reply skeleton come last."""
    import json

    lines = []
    for k, v in info.items():
        if isinstance(v, list) or k in (MEMORY_KEY, MEMORY_SOURCE_KEY):
            continue
        lines.append(f"{k}: {v}")

    contents = info.get("contents", [])
    lines.append("")
    lines.append(f"Panels in this part ({len(contents)}), in reading order:")
    lines.append(", ".join(contents))

    # Every panel of the chapter, when this part holds only some of them -
    # except on part 1, whose reply skeleton lists them all.
    full_manifest = info.get("full_manifest", [])
    if full_manifest != contents and info.get("part_index", 1) > 1:
        lines.append("")
        lines.append(f"Every panel of the chapter ({len(full_manifest)}, in reading order, across every part):")
        lines.append(", ".join(full_manifest))

    # The story so far and the reply skeleton cover the whole chapter, so
    # they are on part 1 only: every part repeating them made the story so far
    # the biggest thing in a long manga's upload.
    if info.get("part_index", 1) > 1:
        lines += ["", "The story so far and the reply skeleton are on part 1's first page."]
        return wrap_lines(lines)
    memory = info.get(MEMORY_KEY)
    lines.append("")
    if isinstance(memory, list) and memory:
        lines.append(f"Story so far, after chapter {info.get(MEMORY_SOURCE_KEY)} (from the memory written with "
                     f"each chapter's narration):")
        lines.extend(memory)
    elif memory:
        lines.append(f"Story so far (the memory written with chapter {info.get(MEMORY_SOURCE_KEY)}'s narration):")
        lines.extend(json.dumps(memory, indent=2, ensure_ascii=False).splitlines())
    else:
        lines.append("Story so far: none - this is the first chapter narrated for this manga.")

    lines.append("")
    lines.extend(reply_skeleton_lines(info))
    return wrap_lines(lines)


def wrap_lines(lines: Sequence[str]) -> list[str]:
    """Lines wrapped to the text page, each continuation indented two past
    the line it continues."""
    import textwrap

    wrapped: list[str] = []
    for line in lines:
        indent = " " * (len(line) - len(line.lstrip(" ")))
        wrapped.extend(textwrap.wrap(line, LINE_WIDTH, subsequent_indent=indent + "  ",
                                     break_on_hyphens=False) or [""])
    return wrapped


def reply_skeleton_lines(info: dict[str, Any]) -> list[str]:
    """The reply already laid out with every panel of the chapter, for the
    LLM to fill in (user request, 2026-10-18): copying ids out of a list is
    where a panel goes missing or two swap. On the first part only - it
    covers the whole chapter, so once is enough. One panel per line, so the
    wrap never splits one, keyed by its id: the `{"panel", "text"}` entries
    of the older shape cost more of the reply than the narration did. The
    memory is what this chapter changes, with the threads open so far
    already in it to keep, close or add to (`THREADS_KEY`)."""
    import json

    ids = info.get("full_manifest", [])
    memory = {"summary": "", "events": [], "characters": {}, "places": {}, "terms": {},
              "threads": list(info.get(THREADS_KEY) or [])}
    lines = ["Reply skeleton: every panel of the chapter, in order. Write each panel's narration as its value,",
             'or "skip REASON"; fill in the memory with what this chapter changes, and reply with the whole',
             "thing as one ```json block.",
             "{",
             '  "narration": {',
             f'    "chapter": {json.dumps(str(info.get("chapter", "")))},',
             '    "problems": [],',
             '    "panels": {']
    lines += [f'      {json.dumps(pid)}: ""{"," if i < len(ids) - 1 else ""}' for i, pid in enumerate(ids)]
    memory_lines = json.dumps(memory, indent=2, ensure_ascii=False).splitlines()
    lines += ["    }", "  },", '  "memory": ' + memory_lines[0], *("  " + line for line in memory_lines[1:]), "}"]
    return lines
