"""Where the standalone worker scripts live, for the isolated per-tool
virtualenvs bootstrap.sh provisions (`.tools/venv-kokoro`,
`.tools/venv-chatterbox`, `.tools/venv-magi`, `.tools/venv-deepseek-ocr`,
...) - one dependency-isolated environment per heavy ML engine so their
conflicting library pins never have to share one Python process.

Which interpreter a tool runs is remanga/tool_envs/ (`ensure_tool`, also
re-exported as `remanga.venvs.get_tool_python`), which installs the
environment if this is its first use - there is no second, locate-only copy
of that lookup here. remanga/workers/ drives the subprocesses."""

from __future__ import annotations

from pathlib import Path

from .roots import REPO_ROOT


def get_scripts_dir(package_relpath: str) -> Path:
    """Path to a `scripts/` directory holding a standalone (no remanga-package-
    import-required) worker script, e.g. get_scripts_dir("audio")."""
    return REPO_ROOT / "remanga" / package_relpath / "scripts"
