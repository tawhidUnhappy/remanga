"""Auto-heal helper for the isolated per-tool virtual environments
bootstrap.sh provisions: parses "missing package" errors out of a worker
subprocess's stderr so remanga/audio/synth.py and remanga/webui/magi_assist.py
can pip-install the gap and retry, instead of just failing.

Path resolution for those environments themselves (REPO_ROOT, TOOLS_DIR,
get_tool_python, get_scripts_dir) now lives in remanga/paths/ - the single
source of truth for every path remanga resolves - and is re-exported below
so every existing `from remanga.venvs import ...` elsewhere in the codebase
keeps working unchanged."""

from __future__ import annotations

import re
from typing import Set

from remanga.paths import REPO_ROOT, TOOLS_DIR, get_scripts_dir, get_tool_python

__all__ = [
    "REPO_ROOT", "TOOLS_DIR", "get_tool_python", "get_scripts_dir", "extract_missing_packages",
]

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
