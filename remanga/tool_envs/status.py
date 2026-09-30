"""What is installed: each tool's state for the setup screen and CLI, and the
environments no tool claims any more."""

from __future__ import annotations

from pathlib import Path

from remanga.tool_envs.catalog import TOOL_NAMES, TOOLS
from remanga.tool_envs.install import is_current, venv_python
from remanga.tool_envs.spec import TOOLS_DIR


def orphan_envs() -> list[Path]:
    """`.tools/venv-*` directories no tool claims any more - what a removed
    TOOLS entry leaves behind. Reported rather than deleted: several GB that
    somebody may still want is not this function's call to make."""
    if not TOOLS_DIR.is_dir():
        return []
    known = {f"venv-{name}" for name in TOOL_NAMES}
    return sorted(p for p in TOOLS_DIR.glob("venv-*") if p.is_dir() and p.name not in known)


def status_rows() -> list[tuple[str, str, str]]:
    """(name, display name, state) for every tool, for the setup screens."""
    rows = []
    for spec in TOOLS:
        if not venv_python(spec.venv_dir):
            state = "not installed"
        elif is_current(spec):
            state = "ready"
        else:
            state = "needs updating"
        rows.append((spec.name, spec.display_name, state))
    return rows
