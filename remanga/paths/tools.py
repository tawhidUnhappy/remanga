"""Locates the isolated per-tool virtualenvs bootstrap.sh provisions
(`.tools/venv-indextts`, `.tools/venv-audio8`, `.tools/venv-magi`, ...) and
their standalone worker scripts - one dependency-isolated environment per
heavy ML engine so their conflicting library pins never have to share one
Python process. See remanga/audio/synth.py and remanga/webui/magi_assist.py
for the subprocess machinery that actually drives these."""

from __future__ import annotations

from pathlib import Path

from .roots import REPO_ROOT, TOOLS_DIR


def get_tool_python(tool_name: str) -> Path:
    """Path to the python interpreter inside `.tools/venv-<tool_name>`."""
    venv_dir = TOOLS_DIR / f"venv-{tool_name}"
    candidates = [venv_dir / "bin" / "python3", venv_dir / "bin" / "python", venv_dir / "Scripts" / "python.exe"]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Isolated environment '.tools/venv-{tool_name}' not found at {venv_dir}.\n"
        f"Run `bash bootstrap.sh` to provision it."
    )


def get_scripts_dir(package_relpath: str) -> Path:
    """Path to a `scripts/` directory holding a standalone (no remanga-package-
    import-required) worker script, e.g. get_scripts_dir("audio")."""
    return REPO_ROOT / "remanga" / package_relpath / "scripts"
