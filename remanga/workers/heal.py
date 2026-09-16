"""Starting a tool's worker process, and healing what its install missed.

Every heavy engine runs in its own `.tools/venv-<name>` (see
remanga/tool_envs/) and announces itself with a ready event on stdout. When
it reports a missing dependency instead - either transformers' own
trust_remote_code check, or a plain unlisted import its remote code happens
to need (matplotlib and einops have both come up) - that package is
installed into the tool's environment and the worker started again, rather
than a session failing over something one pip install fixes.

One implementation for every engine: TTS (audio/synth/), OCR (ocr/engine.py)
and MAGI (webui/magi_assist.py)."""

from __future__ import annotations

import contextlib
import json
import subprocess
from collections.abc import Callable

from remanga.console import console
from remanga.paths import UV_BIN
from remanga.venvs import extract_missing_packages, get_tool_python

# How many DISTINCT missing packages are installed before giving up: a worker
# that keeps naming new ones is broken in a way pip can't fix.
MAX_AUTO_HEAL_ATTEMPTS = 8


def pip_install_into_tool_env(tool_name: str, packages: set) -> bool:
    """Installs `packages` into `.tools/venv-<tool_name>`, preferring this
    repo's own `bin/uv` (that isolated venv has no `pip` module at all)."""
    names = sorted(packages)
    console.print(f"[yellow]Installing missing dependency into .tools/venv-{tool_name}: {' '.join(names)}...[/]")

    uv_bin = UV_BIN
    python = get_tool_python(tool_name)
    cmd = [str(uv_bin), "pip", "install", "--python", str(python), *names] if uv_bin.exists() \
        else [str(python), "-m", "pip", "install", *names]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"[bold red]Failed to install {' '.join(names)} automatically.[/]")
        return False
    console.print(f"[bold green]✓ Installed {' '.join(names)}.[/]")
    return True


def start_worker(
    spawn: Callable[[], subprocess.Popen], *, display_name: str, tool_name: str,
    loading: Callable[[], contextlib.AbstractContextManager] | None = None,
) -> tuple[subprocess.Popen, dict]:
    """Spawns a worker and waits for its ready event, healing a missing
    dependency and retrying when that is what it reports instead. Returns the
    running process and that ready event, which carries whatever the worker
    says about itself - the device it loaded on, say.

    `loading` is an optional context manager around the spawn-and-wait, for a
    caller that wants a spinner while the model loads."""
    attempted: set = set()

    for _ in range(MAX_AUTO_HEAL_ATTEMPTS + 1):
        with loading() if loading is not None else contextlib.nullcontext():
            proc = spawn()
            first_line = proc.stdout.readline()

        if not first_line:
            stderr = proc.stderr.read()
            raise RuntimeError(f"{display_name} worker exited before starting up:\n{stderr}")

        event = json.loads(first_line)
        if event.get("event") == "ready":
            return proc, event

        error_text = event.get("error", "")
        missing = extract_missing_packages(error_text) - attempted
        if not missing:
            raise RuntimeError(f"{display_name} worker failed to load: {error_text}")
        attempted |= missing
        if not pip_install_into_tool_env(tool_name, missing):
            raise RuntimeError(f"{display_name} worker failed to load: {error_text}")
        console.print(f"[dim]Retrying {display_name} worker startup with the newly installed package(s)...[/]")

    raise RuntimeError(
        f"{display_name} worker still fails to load after installing: {', '.join(sorted(attempted))}"
    )
