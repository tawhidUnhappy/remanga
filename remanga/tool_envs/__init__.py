"""The isolated tool environments remanga provisions: each engine or model
(Kokoro-82M, Qwen3-TTS, MAGI v3, faster-whisper) runs in its own
`.tools/venv-<name>`, so torch and its pins never touch the main environment.

    spec.py     what an environment entry is (ToolSpec, InstallStep)
    catalog.py  tools() - the entries, registered by "tool" plug-ins
    install.py  creating, updating and checking the environments
    cli.py      `python -m remanga.tool_envs install|list`

Stdlib only (a plug-in's __init__ registers descriptions and imports nothing
heavy), so bootstrap.sh can run it with none of remanga's own dependencies
involved."""

from __future__ import annotations

from remanga.tool_envs.catalog import tool_names, tool_spec, tools
from remanga.tool_envs.install import (
    backfill_marker,
    build_env,
    default_torch_backend,
    ensure_tool,
    install_tool,
    is_current,
    provision,
    say,
    uv_bin,
    venv_python,
    warn,
)
from remanga.tool_envs.spec import MARKER_NAME, PYTHON_VERSION, REPO_ROOT, TOOLS_DIR, InstallStep, ToolSpec
from remanga.tool_envs.status import orphan_envs, status_rows

__all__ = [
    "MARKER_NAME",
    "PYTHON_VERSION",
    "REPO_ROOT",
    "TOOLS_DIR",
    "InstallStep",
    "ToolSpec",
    "backfill_marker",
    "build_env",
    "default_torch_backend",
    "ensure_tool",
    "install_tool",
    "is_current",
    "orphan_envs",
    "provision",
    "say",
    "status_rows",
    "tool_names",
    "tool_spec",
    "tools",
    "uv_bin",
    "venv_python",
    "warn",
]
