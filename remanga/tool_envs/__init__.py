"""The isolated tool environment remanga provisions: Kokoro-82M runs in
`.tools/venv-kokoro`, so torch and its pins never touch the main environment.

    spec.py     what an environment entry is (ToolSpec, InstallStep)
    catalog.py  TOOLS - the entries themselves
    install.py  creating, updating and checking the environments
    cli.py      `python -m remanga.tool_envs install|list`

Stdlib only, so bootstrap.sh can run it on the main environment's python with
none of remanga's own dependencies involved."""

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
