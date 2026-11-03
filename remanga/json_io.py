"""Shared JSON read/write helpers so every module stops re-implementing open()+json.load/dump."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path | str) -> Any:
    """Reads and parses a JSON file. Raises FileNotFoundError/JSONDecodeError if missing or invalid."""
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def read_json_or(path: Path | str, default: Any = None) -> Any:
    """Reads JSON, returning `default` if the file is missing, empty, or unparsable."""
    try:
        return read_json(path)
    except Exception:
        return default


def write_json(path: Path | str, data: Any, indent: int = 2) -> None:
    """Serializes `data` as indented JSON, creating parent directories as needed.
    Writes to a temp file in the same directory, then atomically renames it over
    the target (Path.replace) - a write-in-place here would leave `path` holding a
    truncated/corrupt file if the process is killed mid-write."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
        Path(tmp_path).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink()
        raise


# Minimum byte size of real, LLM-pasted JSON. Placeholders are written empty;
# this guards against a whitespace-only save being mistaken for content.
PLACEHOLDER_MAX_BYTES = 10


def has_real_json_content(path: Path | str) -> bool:
    """True if `path` exists and holds more than a blank placeholder - the shared
    check for whether narration.json has been written yet."""
    p = Path(path)
    return p.exists() and p.stat().st_size > PLACEHOLDER_MAX_BYTES


class ReplyObject(dict):
    """A JSON object from a pasted reply that remembers the keys it held more
    than once: json.loads keeps only the last, and in a reply keyed by panel
    id a panel given twice must not pass unnoticed."""
    duplicates: tuple[str, ...] = ()


def _reply_object(pairs: list[tuple[str, Any]]) -> ReplyObject:
    obj = ReplyObject(pairs)
    if len(obj) < len(pairs):
        seen: set[str] = set()
        repeated = []
        for key, _ in pairs:
            if key in seen:
                repeated.append(key)
            seen.add(key)
        obj.duplicates = tuple(repeated)
    return obj


def json_from_reply(raw: str) -> Any:
    """The JSON document inside a reply pasted from a chat model. The model is
    asked for exactly one fenced block and nothing else, but a paste can still
    bring the fence along, a stray sentence around it, or a byte-order mark.
    Raises json.JSONDecodeError when there is no JSON to be found."""
    text = raw.lstrip("\ufeff").strip()
    fenced = re.search(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text, object_pairs_hook=_reply_object)


def json_blocks_from_reply(raw: str) -> list[Any]:
    """Every JSON document in a pasted reply, in order: each fenced block, or -
    with no fences - each top-level {...} one after another. Raises
    json.JSONDecodeError when there is none."""
    text = raw.lstrip("\ufeff").strip()
    fenced = re.findall(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```", text, re.DOTALL)
    if fenced:
        return [json.loads(block, object_pairs_hook=_reply_object) for block in fenced]
    decoder, blocks, i = json.JSONDecoder(object_pairs_hook=_reply_object), [], 0
    while True:
        i = text.find("{", i)
        if i == -1:
            break
        document, i = decoder.raw_decode(text, i)
        blocks.append(document)
    if not blocks:
        return [json.loads(text, object_pairs_hook=_reply_object)]
    return blocks
