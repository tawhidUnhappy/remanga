"""Resolves the isolated per-tool virtual environments bootstrap.sh provisions
alongside the main `.venv` - one per heavy ML dependency (IndexTTS-2.5, MAGI v3)
so their conflicting library requirements (e.g. two different `transformers`
pins) never have to share one Python process. The main env orchestrates these
as subprocesses; see remanga/audio/synth.py and remanga/webui/magi_assist.py.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_tool_python(tool_name: str) -> Path:
    """Path to the python interpreter inside `.venv-<tool_name>`."""
    venv_dir = REPO_ROOT / f".venv-{tool_name}"
    candidates = [venv_dir / "bin" / "python3", venv_dir / "bin" / "python", venv_dir / "Scripts" / "python.exe"]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Isolated environment '.venv-{tool_name}' not found at {venv_dir}.\n"
        f"Run `bash bootstrap.sh` to provision it."
    )


def get_scripts_dir(package_relpath: str) -> Path:
    """Path to a `scripts/` directory holding a standalone (no remanga-package-
    import-required) worker script, e.g. get_scripts_dir("audio")."""
    return REPO_ROOT / "remanga" / package_relpath / "scripts"
