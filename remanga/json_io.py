"""Shared JSON read/write helpers so every module stops re-implementing open()+json.load/dump."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path | str) -> Any:
    """Reads and parses a JSON file. Raises FileNotFoundError/JSONDecodeError if missing or invalid."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_json_or(path: Path | str, default: Any = None) -> Any:
    """Reads JSON, returning `default` if the file is missing, empty, or unparsable."""
    try:
        return read_json(path)
    except Exception:
        return default


def write_json(path: Path | str, data: Any, indent: int = 2) -> None:
    """Serializes `data` as indented JSON, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)
