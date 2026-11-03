"""Narration replies scored against a chapter's gold transcript (gold.py), blind.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-narration-eval/score.py sheet PROJECT CHAPTER GOLD.txt OUT \
        NAME=reply.txt [NAME=reply.txt ...]
    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-narration-eval/score.py tally OUT

`sheet` gives every reply a random letter (the key goes to OUT/key.json - leave it unread until the tally) and
writes OUT/sheet.md for a judge: panel by panel, the gold lines numbered (L1, L2, ...) with who says them,
then what each reply tells there - its own text, or, for a panel folded into a neighbour, the neighbour's
text. It also writes OUT/auto.json, what a program can measure: does the reply check out first time
(narration/check.py), the style warnings, panels narrated and folded, words, and the reply's size.

The judge reads sheet.md and writes OUT/judgments.json - only what is wrong; anything not listed was right:

    {"X": {"missing": ["L12"], "partial": ["L40"], "speaker": ["L3"], "order": ["002_005_04"],
           "invented": [{"panel": "002_009_01", "note": "names the maid, who is never named"}],
           "blurbs": 0}}

missing: a gold line not told at all; partial: told with part of its content lost; speaker: told in the wrong
mouth (or given to someone when the chapter shows nobody); order: a panel whose lines are told in an order
that changes their sense; invented: something told that the panels and the story so far do not show;
blurbs: publisher blurbs or credits narrated as story. `tally` prints the table, by name."""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

from remanga.narration import check_reply, panel_files, read_reply

COUNTED = ("speech", "thought", "caption", "sign")


def read_gold(path: Path) -> list[dict]:
    """The gold lines in order, the counted ones numbered L1, L2, ..."""
    lines, n = [], 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        panel, speaker, kind, text = (part.strip() for part in raw.split("|", 3))
        kind = kind.split()[0]
        line = {"panel": panel, "speaker": speaker, "kind": kind, "text": text}
        if kind in COUNTED:
            n += 1
            line["id"] = f"L{n}"
        lines.append(line)
    return lines


def told_where(entries: list[dict]) -> dict[str, tuple[str, str]]:
    """panel id -> (where its content is told, that text): itself, or the panel a fold carries it to."""
    narrated = [e["panel"] for e in entries if not e.get("skip")]
    text = {e["panel"]: e.get("text") or "" for e in entries}
    out = {}
    for _i, entry in enumerate(entries):
        panel, skip = entry["panel"], entry.get("skip")
        if not skip:
            out[panel] = (panel, text[panel])
        elif skip in ("merged", "merged_prev"):
            pool = [p for p in narrated if p > panel] if skip == "merged" else [p for p in narrated if p < panel]
            target = (pool[0] if skip == "merged" else pool[-1]) if pool else None
            out[panel] = (target or f"({skip}, nothing to carry it)", text.get(target, ""))
        else:
            out[panel] = (f"(skip {skip})", "")
    return out


def auto_metrics(project: str, chapter: str, reply: Path) -> tuple[dict, list[dict] | None]:
    ids = [p.stem for p in panel_files(project, chapter)]
    try:
        doc, memory = read_reply(reply)
    except (json.JSONDecodeError, ValueError, IndexError) as error:
        return {"parses": False, "error": str(error)[:200]}, None
    check = check_reply(doc, ids, chapter)
    entries = [e for e in doc.get("panels") or [] if isinstance(e, dict) and e.get("panel") in ids]
    raw = reply.read_text(encoding="utf-8")
    warnings = {}
    for warning in check.warnings:
        kind = ("quotation marks/contractions" if "voice rules" in warning else "too short" if "words - is" in warning
                else "too long" if "on one picture" in warning else "other")
        warnings[kind] = warnings.get(kind, 0) + 1
    return {
        "parses": True, "first_try_ok": not check.errors, "errors": check.errors[:10],
        "warnings": warnings,
        "narrated": sum(1 for e in entries if not e.get("skip")),
        "folded": sum(1 for e in entries if e.get("skip") in ("merged", "merged_prev")),
        "skipped": sum(1 for e in entries if e.get("skip") not in (None, "", "merged", "merged_prev")),
        "words": sum(len((e.get("text") or "").split()) for e in entries),
        "reply_chars": len(raw),
        "memory_chars": len(json.dumps(memory or {}, ensure_ascii=False)),
    }, entries


def sheet(project: str, chapter: str, gold_path: Path, out: Path, replies: dict[str, Path]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    letters = list("XYZWVU")[:len(replies)]
    random.shuffle(letters)
    key = dict(zip(letters, replies, strict=False))
    gold = read_gold(gold_path)
    auto, told = {}, {}
    for letter, name in key.items():
        metrics, entries = auto_metrics(project, chapter, replies[name])
        auto[letter] = metrics
        told[letter] = told_where(entries) if entries else {}
    rows = [f"# Chapter {chapter}: {len(replies)} replies, {sum(1 for g in gold if 'id' in g)} gold lines", "",
            "For each reply, list in judgments.json only what is wrong (see score.py). A folded panel shows the "
            "text of the panel that carries it.", ""]
    by_panel: dict[str, list[dict]] = {}
    for line in gold:
        by_panel.setdefault(line["panel"], []).append(line)
    for panel in [p.stem for p in panel_files(project, chapter)]:
        rows.append(f"### {panel}")
        for line in by_panel.get(panel, []):
            tag = line.get("id") or f"({line['kind']})"
            rows.append(f"{tag} {line['speaker']}: {line['text']}" if line.get("id") else f"{tag} {line['text']}")
        for letter in sorted(key):
            where, text = told[letter].get(panel, ("(missing)", ""))
            rows.append(f"{letter}: {text}" if where == panel else f"{letter}: [{where}] {text}")
        rows.append("")
    (out / "sheet.md").write_text("\n".join(rows), encoding="utf-8")
    (out / "auto.json").write_text(json.dumps(auto, indent=2) + "\n", encoding="utf-8")
    (out / "key.json").write_text(json.dumps({k: str(v) for k, v in key.items()}, indent=2) + "\n",
                                  encoding="utf-8")
    print(f"{out / 'sheet.md'}: {len(rows)} lines; auto.json written; key.json written (unread until the tally)")


def tally(out: Path) -> None:
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))
    auto = json.loads((out / "auto.json").read_text(encoding="utf-8"))
    judged = json.loads((out / "judgments.json").read_text(encoding="utf-8"))
    total = int(re.search(r"(\d+) gold lines", (out / "sheet.md").read_text(encoding="utf-8")).group(1))
    print(f"{'reply':<34} {'told':>6} {'whole':>6} {'mouth':>6} {'invent':>6} {'order':>5} {'first try':>9} "
          f"{'words':>6} {'reply chars':>11}")
    for letter in sorted(key):
        j, a = judged.get(letter, {}), auto.get(letter, {})
        missing, partial = len(j.get("missing", [])), len(j.get("partial", []))
        told = total - missing
        print(f"{key[letter] + ' (' + letter + ')':<34} {told / total:>6.1%} "
              f"{(told - partial) / total:>6.1%} {1 - len(j.get('speaker', [])) / max(1, told):>6.1%} "
              f"{len(j.get('invented', [])):>6} {len(j.get('order', [])):>5} "
              f"{'yes' if a.get('first_try_ok') else 'NO':>9} {a.get('words', 0):>6} {a.get('reply_chars', 0):>11,}")


def main() -> None:
    if len(sys.argv) >= 7 and sys.argv[1] == "sheet":
        replies = dict(arg.split("=", 1) for arg in sys.argv[6:])
        sheet(sys.argv[2], sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5]),
              {name: Path(path) for name, path in replies.items()})
    elif len(sys.argv) == 3 and sys.argv[1] == "tally":
        tally(Path(sys.argv[2]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
