"""Every isolated tool environment remanga provisions, and how.

Each heavy ML tool runs in its own `.tools/venv-<name>` (see
remanga/paths/tools.py) because their dependency pins genuinely conflict -
MAGI v3 needs transformers<4.52, DeepSeek-OCR-2 pins ==4.46.3, Chatterbox
pins ==5.2.0, and nothing guarantees any two of them would ever agree on one
resolution.

This package is the single description of those environments: what each one
is called, what goes into it, and why. It is what bootstrap.sh provisions
from, what `remanga setup-tools` repairs from, and what a tool installs
itself from the first time it is used (remanga/venvs.py:get_tool_python).

    spec.py     what an environment entry is (ToolSpec, InstallStep)
    catalog.py  TOOLS - the entries themselves
    install.py  creating, updating and checking the environments
    cli.py      `python -m remanga.tool_envs install|list`

Adding a tool is a TOOLS entry plus the code that drives it; removing one is
deleting both. Nothing else in the tree hand-writes a venv path, an install
command or a package list, so neither direction can leave half a tool behind
in a shell script nobody reads. Before this existed, adding one meant
editing a block of bootstrap.sh by hand, and removing one meant remembering
that block was there.

Stdlib only, so the interpreter is all it needs: bootstrap.sh runs
`python -m remanga.tool_envs install` on the main environment's python with
none of remanga's own dependencies involved.
"""

from __future__ import annotations

from remanga.tool_envs.catalog import TOOL_NAMES, TOOLS, tool_spec
from remanga.tool_envs.install import (
    backfill_marker,
    default_torch_backend,
    ensure_tool,
    install_tool,
    is_current,
    orphan_envs,
    provision,
    say,
    status_rows,
    uv_bin,
    venv_python,
    warn,
)
from remanga.tool_envs.spec import MARKER_NAME, PYTHON_VERSION, REPO_ROOT, TOOLS_DIR, InstallStep, ToolSpec

__all__ = [
    "MARKER_NAME",
    "PYTHON_VERSION",
    "REPO_ROOT",
    "TOOLS",
    "TOOLS_DIR",
    "TOOL_NAMES",
    "InstallStep",
    "ToolSpec",
    "backfill_marker",
    "default_torch_backend",
    "ensure_tool",
    "install_tool",
    "is_current",
    "orphan_envs",
    "provision",
    "say",
    "status_rows",
    "tool_spec",
    "uv_bin",
    "venv_python",
    "warn",
]
