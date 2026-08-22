"""Resolves the isolated per-tool virtual environments bootstrap.sh provisions
alongside the main `.venv` - one per heavy ML dependency (IndexTTS-2.5, MAGI v3)
so their conflicting library requirements (e.g. two different `transformers`
pins) never have to share one Python process. The main env orchestrates these
as subprocesses; see remanga/audio/synth.py and remanga/webui/magi_assist.py.

All of them live under `.tools/` for tidy management - `.tools/venv-indextts`,
`.tools/venv-magi`, etc. - one place to eyeball or `rm -rf` if something needs
a clean reinstall, instead of scattered `.venv-*` siblings of the repo root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / ".tools"

# Two shapes of "you're missing a package" error get auto-healed (see
# extract_missing_packages() below):
#   1. transformers' own trust_remote_code check: "This modeling file requires
#      the following packages that were not found in your environment: foo,
#      bar. Run `pip install foo bar`" - can list several packages at once.
#   2. A plain Python import failure the remote code didn't declare at all:
#      "No module named 'foo'" (ModuleNotFoundError/ImportError) - one at a time.
_HF_MISSING_PKG_RE = re.compile(
    r"the following packages that were not found in your environment:\s*([^.]+)\.", re.IGNORECASE
)
_PLAIN_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([\w][\w.]*)['\"]")

# Import name -> actual pip package name, for the common cases where they differ.
_IMPORT_TO_PIP_NAME = {
    "cv2": "opencv-python",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
}


def extract_missing_packages(error_text: str) -> Set[str]:
    """Parses an error message for missing package name(s), pip-installable
    as-is. Returns an empty set if the message doesn't match a known shape."""
    match = _HF_MISSING_PKG_RE.search(error_text)
    if match:
        return {pkg.strip() for pkg in match.group(1).replace(",", " ").split() if pkg.strip()}

    match = _PLAIN_MISSING_MODULE_RE.search(error_text)
    if match:
        top_level = match.group(1).split(".")[0]
        return {_IMPORT_TO_PIP_NAME.get(top_level, top_level)}

    return set()


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
