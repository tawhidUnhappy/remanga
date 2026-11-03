"""Narration from an older remanga's zip, in remanga's own format.

The zip's chapter folders hold `narration.json` ([{"image": "chapterN_001.png", "narration": text}, ...],
one line per cut panel, in order) beside the cut panels; they were put in the project's import_zip/ by the
setup. Each chapter is checked before anything is written - its pages downloaded and checked, its old
panels all there and named exactly as the narration names them, its marks cut into as many new panels -
and then written as chapters/chapter_N/narration.json with the memory section, the text made to fit the
narration rules by code (no quotation marks, no contractions): quotes dropped, contractions spelled out."""

from __future__ import annotations

import json
import os
import re

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json_or
from remanga.narration import page_files, panel_files
from remanga.paths import get_chapter_dir, get_project_dir

_QUOTE_MARKS = '"“”„«»‘’‚‹›`'
_SPELLED = [
    (r"\bcan't\b", "cannot"), (r"\bwon't\b", "will not"), (r"\bshan't\b", "shall not"),
    (r"\bain't\b", "is not"), (r"\blet's\b", "let us"), (r"\bI'm\b", "I am"),
    (r"\b(\w+)n't\b", r"\1 not"), (r"\b(\w+)'re\b", r"\1 are"), (r"\b(\w+)'ve\b", r"\1 have"),
    (r"\b(\w+)'ll\b", r"\1 will"),
    (r"\b(he|she|it|that|there|here|what|who|where|how)'s\b", r"\1 is"),
    (r"\b(I|you|he|she|it|we|they|who)'d\b", r"\1 would"),
]


def fit_rules(text: str) -> str:
    """The line with contractions spelled out and quotation marks dropped. A
    possessive 's and a name's apostrophe (Xiao Qi'er) stay."""
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    for pattern, replacement in _SPELLED:
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r"(^|[\s(\[])'|(?<![sS])'(?=[\s.,;:!?)\]]|$)", r"\1", text)   # a single quote used as a quote mark
    text = text.translate({ord(c): None for c in _QUOTE_MARKS})
    return re.sub(r"\s+", " ", text).strip()


def _memory(project: str, chapter: str, title: str) -> dict:
    progress = read_json_or(get_project_dir(project) / "import_zip" / "story_progress.json", {})
    names = (get_project_dir(project) / "import_zip" / "chracters.txt")
    characters = {}
    for entry in progress.get("characters") or []:
        if isinstance(entry, dict) and entry.get("name"):
            characters[entry["name"]] = "; ".join(str(v) for k, v in entry.items()
                                                  if k in ("role", "description") and v)
    if not characters and names.exists():
        characters = {line.strip(): "" for line in names.read_text(encoding="utf-8").splitlines() if line.strip()}
    lore = progress.get("world_lore") or {}
    return {"series_title": title, "last_chapter": str(chapter), "characters": characters,
            "places": lore.get("locations") or {}, "key_events": [], "open_threads": []}


def import_chapter(project: str, chapter: str, config: RemangaConfig) -> bool:
    """Checks the chapter, writes its narration.json. True when written."""
    from remanga.workflow.panels import cut_panels
    from remanga.workflow.video import check_chapter

    ref = get_project_dir(project) / "import_zip" / f"{int(float(chapter)):02d}"
    problems: list[str] = []
    if not page_files(project, chapter):
        problems.append("its pages are not downloaded")
    old = sorted(p.name for p in (ref / "panels").glob("*.png"))
    lines = read_json_or(ref / "narration.json", None)
    if not lines or not old:
        console.print(f"[yellow]Chapter {chapter}: no old narration or panels in import_zip - skipped.[/]")
        return False
    if [line["image"] for line in lines] != old:
        problems.append(f"the narration names {len(lines)} images, the old panels are {len(old)}, and they differ")
    try:
        cut_panels(project, chapter, config)
    except FileNotFoundError as error:
        problems.append(str(error))
    ids = [p.stem for p in panel_files(project, chapter)]
    if len(ids) != len(lines):
        problems.append(f"{len(ids)} new panels cut but {len(lines)} narration lines")
    if problems:
        console.print(f"[yellow]Chapter {chapter}: not imported - {_esc('; '.join(problems))}[/]")
        return False
    rows = []
    for panel, line in zip(ids, lines, strict=True):
        text = fit_rules(str(line["narration"]))
        rows.append({"panel": panel, "text": text} if text else {"panel": panel, "skip": "blank", "text": ""})
    from remanga.paths import load_project_metadata

    title = load_project_metadata(project).get("manga_title", project)
    doc = {"narration": {"chapter": str(chapter), "problems": [], "panels": rows},
           "memory": _memory(project, chapter, title)}
    target = get_chapter_dir(project, chapter) / "narration.json"
    partial = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    partial.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    partial.replace(target)
    result = check_chapter(project, chapter, config)
    console.print(f"[green]✓ Chapter {chapter}: {len(rows)} panels narrated from the old narration[/] "
                  f"-> {result['state']}")
    for line in result["errors"] + result["warnings"]:
        console.print(f"  [yellow]- {_esc(str(line))}[/]")
    return result["state"] != "problems"



