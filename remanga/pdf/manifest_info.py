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


# Characters per line on the text page (11pt Helvetica on a US Letter page
# with 54pt margins holds about this many).
LINE_WIDTH = 95
MEMORY_KEY = "story_so_far"
MEMORY_SOURCE_KEY = "story_so_far_from_chapter"
# The marked pages in this part, and what each one holds: the key to reading
# the images that follow, since a page image and the panels cut from it look
# nothing alike until you know which is which. Both are `extra` on
# build_part_info, filled in by pdf/builder.py.
PAGES_KEY = "pages_in_this_part"
PAGE_PANELS_KEY = "panels_per_page"


def info_to_text_lines(info: dict[str, Any]) -> list[str]:
    """A build_part_info() dict as plain lines for the PDF's text page(s),
    wrapped to the page. The page lists get labeled sections of their own,
    and the story so far (MEMORY_KEY, the previous chapter's memory section) comes last,
    as indented JSON."""
    import json
    import textwrap

    lines = []
    for k, v in info.items():
        if isinstance(v, (list, dict)) or k in (MEMORY_KEY, MEMORY_SOURCE_KEY):
            continue
        lines.append(f"{k}: {v}")

    pages = info.get(PAGES_KEY) or []
    panels_per_page = info.get(PAGE_PANELS_KEY) or {}
    if pages:
        lines.append("")
        lines.append(f"Pages in this part ({len(pages)}), in reading order. Each is a whole page of the "
                     f"chapter with its panels outlined and labelled, and the panels cut from it follow it "
                     f"as their own images:")
        for page in pages:
            held = panels_per_page.get(page) or []
            lines.append(f"  {page}: " + (", ".join(held) if held
                                          else "no panels marked - context only, nothing to narrate"))

    contents = info.get("contents", [])
    lines.append("")
    lines.append(f"Panels in this part ({len(contents)}), in reading order - these are what you narrate, "
                 f"one entry each:")
    lines.append(", ".join(contents))

    full_manifest = info.get("full_manifest", [])
    if full_manifest != contents:
        lines.append("")
        lines.append(f"Every panel of the chapter ({len(full_manifest)}, in reading order, across every part):")
        lines.append(", ".join(full_manifest))

    memory = info.get(MEMORY_KEY)
    lines.append("")
    if memory:
        lines.append(f"Story so far (the memory written with chapter {info.get(MEMORY_SOURCE_KEY)}'s narration):")
        lines.extend(json.dumps(memory, indent=2, ensure_ascii=False).splitlines())
    else:
        lines.append("Story so far: none - this is the first chapter narrated for this manga.")

    wrapped: list[str] = []
    for line in lines:
        indent = " " * (len(line) - len(line.lstrip(" ")))
        wrapped.extend(textwrap.wrap(line, LINE_WIDTH, subsequent_indent=indent + "  ",
                                     break_on_hyphens=False) or [""])
    return wrapped
