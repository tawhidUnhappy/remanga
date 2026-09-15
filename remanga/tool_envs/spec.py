"""What one tool environment is - its name and what goes into it - and where
every environment lives on disk."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / ".tools"
PYTHON_VERSION = "3.11"

# Written into an environment once its install finishes, so a later run can
# tell "up to date with its TOOLS entry" from "half-installed, or built from
# an older entry". Changing an entry - a new package, a different pin -
# therefore re-syncs that environment the next time it is used, instead of
# waiting for somebody to think of re-running bootstrap.
MARKER_NAME = ".remanga-tool.json"


@dataclass(frozen=True)
class InstallStep:
    """One `uv pip install` into a tool's environment.

    `torch_backend` puts this machine's wheel index behind the install (see
    remanga/hardware.py) and belongs on every step that pulls a
    torch-ecosystem package: a later step that re-resolves torch as a
    dependency will otherwise happily replace a machine-matched build with
    the plain PyPI one. `no_deps` installs the packages on their own, for a
    package whose own pins cannot be honoured on this machine."""

    packages: tuple[str, ...]
    torch_backend: bool = True
    no_deps: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """One isolated environment: what it is called, and what goes in it."""

    name: str
    display_name: str
    summary: str
    steps: tuple[InstallStep, ...]

    @property
    def venv_dir(self) -> Path:
        return TOOLS_DIR / f"venv-{self.name}"

    @property
    def fingerprint(self) -> str:
        """Identifies this entry's install, so a changed entry is noticed.
        Only what is actually installed counts - renaming a display name or
        rewording a summary must not trigger a re-install."""
        payload = json.dumps(
            [[list(step.packages), step.torch_backend, step.no_deps] for step in self.steps],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
