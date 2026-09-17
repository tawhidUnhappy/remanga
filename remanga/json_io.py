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
    check for whether narration.json or memory.json has been written yet."""
    p = Path(path)
    return p.exists() and p.stat().st_size > PLACEHOLDER_MAX_BYTES


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
    return json.loads(text)
