"""The story so far: every narrated chapter's memory, folded in reading order.

A reply's memory section (prompts/narration.md) holds what that chapter changed: a summary of it and its
events, the characters, places and terms it brought in or changed, and the threads still open after it.
remanga keeps everything else, so a reply never writes the whole story out again - that copy grew with
every chapter until it was most of the reply, read and written again each time.

An older reply's memory holds the whole story instead, as it stood after its chapter. One of those starts
the fold afresh, and the chapters after it add their changes; its long entries stay until a later chapter
writes them again.

Nothing is stored but the chapters' narration.json files - the story so far is rebuilt from them whenever
it is asked for (narration/document.py), so a chapter's PDF only ever sees the chapters before it, and a
chapter narrated again changes the story for every chapter after it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Sections of name -> who or what it is now; a null value takes the name out.
ENTRIES = ("characters", "places", "terms")
# A change record's sections, in the order the reply skeleton gives them.
CHANGE_KEYS = ("summary", "events", *ENTRIES, "threads")
# Only a whole-story memory (the older shape) has these.
WHOLE_STORY_KEYS = ("key_events", "open_threads", "last_chapter", "series_title")
# The latest chapters are told event by event; the ones before them by their
# summaries, so the story so far grows by a line a chapter, not a paragraph.
RECENT_IN_FULL = 2

_HEADINGS = {"characters": "Characters (by the names to keep using):", "places": "Places:", "terms": "Terms:"}


@dataclass
class Story:
    entries: dict[str, dict[str, str]] = field(default_factory=lambda: {key: {} for key in ENTRIES})
    threads: list[str] = field(default_factory=list)
    # A whole-story memory's key events, and the chapter it was written with.
    earlier: list[str] = field(default_factory=list)
    earlier_through: str | None = None
    # (chapter, summary, events) for every chapter folded in as a change record.
    chapters: list[tuple[str, str, list[str]]] = field(default_factory=list)
    # Sections a whole-story memory had of its own, kept as they were.
    extra: dict[str, Any] = field(default_factory=dict)
    through: str | None = None


def is_whole_story(memory: dict[str, Any]) -> bool:
    return any(key in memory for key in WHOLE_STORY_KEYS)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def add_chapter(story: Story | None, chapter: str, memory: dict[str, Any]) -> Story:
    """The story with one more chapter's memory folded in."""
    if is_whole_story(memory):
        story = Story(earlier=[_text(e) for e in memory.get("key_events") or []], earlier_through=str(chapter),
                      threads=[_text(t) for t in memory.get("open_threads") or []])
        for key in ENTRIES:
            story.entries[key] = {str(name): _text(value) for name, value in (memory.get(key) or {}).items()}
        story.extra = {key: value for key, value in memory.items()
                       if key not in (*WHOLE_STORY_KEYS, *ENTRIES) and value}
    else:
        story = story or Story()
        for key in ENTRIES:
            for name, value in (memory.get(key) or {}).items():
                if value is None:
                    story.entries[key].pop(str(name), None)
                else:
                    story.entries[key][str(name)] = _text(value)
        if isinstance(memory.get("threads"), list):
            story.threads = [_text(t) for t in memory["threads"]]
        story.chapters.append((str(chapter), _text(memory.get("summary") or ""),
                               [_text(e) for e in memory.get("events") or []]))
    story.through = str(chapter)
    return story


def story_lines(story: Story, threads: bool = True) -> list[str]:
    """The story so far as plain lines for a text page: who and what, the
    threads still open, then what has happened - the latest chapters event by
    event, the ones before by their summaries."""
    lines: list[str] = []
    for key in ENTRIES:
        if story.entries[key]:
            lines.append(_HEADINGS[key])
            lines += [f"- {name}: {value}" if value else f"- {name}" for name, value in story.entries[key].items()]
    for key, value in story.extra.items():
        lines.append(f"{key}:")
        lines += ([f"- {_text(v)}" for v in value] if isinstance(value, list)
                  else [f"- {k}: {_text(v)}" for k, v in value.items()] if isinstance(value, dict)
                  else [f"- {_text(value)}"])
    if threads and story.threads:
        lines.append("Still open:")
        lines += [f"- {thread}" for thread in story.threads]
    if story.earlier or story.chapters:
        lines.append("What has happened:")
    if story.earlier:
        lines.append(f"Up to chapter {story.earlier_through}:")
        lines += [f"- {event}" for event in story.earlier]
    recent = len(story.chapters) - RECENT_IN_FULL
    for i, (chapter, summary, events) in enumerate(story.chapters):
        if i >= recent and events:
            lines.append(f"Chapter {chapter}:")
            lines += [f"- {event}" for event in events]
        else:
            lines.append(f"Chapter {chapter}: {summary or ' '.join(events)}")
    return lines


def memory_problems(memory: Any) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a reply's memory section: a change record whose
    sections have the wrong shape can't be folded into the story so far. A
    whole-story memory (the older shape) still reads."""
    if not isinstance(memory, dict):
        return ['"memory" must be a JSON object - what this chapter changed in the story'], []
    if is_whole_story(memory):
        return [], ["the memory writes the whole story out again - only what this chapter changed is needed "
                    "(prompts/narration.md)"]
    errors, warnings = [], []
    if not isinstance(memory.get("summary", ""), str):
        errors.append('memory "summary" must be a string - this chapter in a sentence or two')
    elif not str(memory.get("summary") or "").strip():
        warnings.append('memory has no "summary" - later chapters will see this one only through its events')
    for key in ("events", "threads"):
        value = memory.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f'memory "{key}" must be a list of strings')
    for key in ENTRIES:
        value = memory.get(key, {})
        if not isinstance(value, dict) or not all(isinstance(v, str) or v is None for v in value.values()):
            errors.append(f'memory "{key}" must be an object of name: text (null takes a name out)')
    unknown = sorted(set(memory) - set(CHANGE_KEYS))
    if unknown:
        warnings.append(f"memory: ignored unknown section(s) {', '.join(unknown)}")
    return errors, warnings
