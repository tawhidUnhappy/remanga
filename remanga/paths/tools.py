"""Where the standalone worker scripts live, run by the isolated tool
virtualenv (`.tools/venv-kokoro`) - see remanga/tool_envs/ and remanga/workers/."""

from __future__ import annotations

from pathlib import Path

from .roots import REPO_ROOT


def get_scripts_dir(package_relpath: str) -> Path:
    """Path to a `scripts/` directory holding a standalone (no remanga-package-
    import-required) worker script, e.g. get_scripts_dir("audio")."""
    return REPO_ROOT / "remanga" / package_relpath / "scripts"
