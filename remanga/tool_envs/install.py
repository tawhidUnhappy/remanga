"""Creating, updating and checking the environments catalog.py describes:
all of them at once for bootstrap.sh and `remanga setup-tools` (provision),
one on demand the first time a tool is used (ensure_tool)."""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from remanga.tool_envs.catalog import TOOL_NAMES, TOOLS, tool_spec
from remanga.tool_envs.spec import MARKER_NAME, PYTHON_VERSION, REPO_ROOT, TOOLS_DIR, ToolSpec


def say(message: str) -> None:
    print(f"[+] {message}", flush=True)


def warn(message: str) -> None:
    print(f"[-] {message}", file=sys.stderr, flush=True)


def uv_bin() -> Path | None:
    """This repo's own bundled uv. Never the ambient one: bootstrap.sh
    installs it here precisely so provisioning does not depend on what
    happens to be on PATH."""
    for candidate in (REPO_ROOT / "bin" / "uv", REPO_ROOT / "bin" / "uv.exe"):
        if candidate.exists():
            return candidate
    return None


def venv_python(venv_dir: Path) -> Path | None:
    """The interpreter inside an existing environment, or None."""
    for candidate in (venv_dir / "bin" / "python3", venv_dir / "bin" / "python",
                      venv_dir / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


def _marker(spec: ToolSpec) -> dict:
    try:
        return json.loads((spec.venv_dir / MARKER_NAME).read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_current(spec: ToolSpec) -> bool:
    """Whether this environment was installed from the entry as it reads
    now. An environment with NO marker at all - one bootstrap.sh installed
    by hand before this module existed, or one this module installed before
    its first fingerprint - is treated as current rather than stale: the
    marker exists to catch an entry that changed since its install, not to
    force a reinstall of something already working the moment this
    tracking was added. `backfill_marker` below stamps one on it so later
    runs don't have to keep making that same assumption."""
    marker = _marker(spec)
    return "fingerprint" not in marker or marker["fingerprint"] == spec.fingerprint


def backfill_marker(spec: ToolSpec, torch_backend: str) -> None:
    """Writes a marker for an environment that already works but has none -
    see is_current. A no-op if one is already there."""
    if _marker(spec):
        return
    # best-effort - a write failure just means this check runs again next time
    with contextlib.suppress(OSError):
        (spec.venv_dir / MARKER_NAME).write_text(json.dumps({
            "name": spec.name, "fingerprint": spec.fingerprint, "torch_backend": torch_backend,
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "backfilled": True,
        }, indent=2) + "\n", encoding="utf-8")


def default_torch_backend() -> str:
    """The wheel index this machine wants, from the one module that decides
    that (remanga/hardware.py). Falls back to plain PyPI rather than to CPU
    wheels: a wrong guess that is merely slower to download beats one that
    silently installs a CPU-only torch onto a GPU machine."""
    try:
        from remanga.hardware import detect_cached
    except Exception:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        try:
            from hardware import detect_cached
        except Exception:
            return "default"
    try:
        return detect_cached().torch_backend or "default"
    except Exception:
        return "default"


def install_tool(spec: ToolSpec, torch_backend: str | None = None, *, force: bool = False) -> bool:
    """Creates (or updates) one tool's environment. Returns whether it worked.

    Never raises: provisioning is a long sequence of independent steps and a
    caller - bootstrap.sh, `setup-tools`, a first use - always wants the
    other tools to carry on, with a summary at the end of what didn't."""
    uv = uv_bin()
    if uv is None:
        warn(f"cannot install {spec.display_name}: bin/uv is missing - run `bash bootstrap.sh` first")
        return False

    backend = torch_backend or default_torch_backend()
    if force and spec.venv_dir.exists():
        shutil.rmtree(spec.venv_dir, ignore_errors=True)

    say(f"{spec.display_name} environment ({spec.venv_dir.name}) [{backend} wheels]...")
    if subprocess.run([str(uv), "venv", str(spec.venv_dir), "--python", PYTHON_VERSION,
                       "--allow-existing"]).returncode != 0:
        warn(f"could not create {spec.venv_dir}")
        return False

    for index, step in enumerate(spec.steps, start=1):
        cmd = [str(uv), "pip", "install", "--python", str(spec.venv_dir)]
        if step.torch_backend and backend not in ("", "default"):
            cmd += ["--torch-backend", backend]
        if step.no_deps:
            cmd.append("--no-deps")
        cmd += list(step.packages)
        if subprocess.run(cmd).returncode != 0:
            warn(f"{spec.display_name} install step {index}/{len(spec.steps)} failed")
            return False

    (spec.venv_dir / MARKER_NAME).write_text(json.dumps({
        "name": spec.name,
        "fingerprint": spec.fingerprint,
        "torch_backend": backend,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2) + "\n", encoding="utf-8")
    return True


def ensure_tool(name: str) -> Path:
    """The interpreter for `.tools/venv-<name>`, installed first if need be.

    This is what makes a tool's environment arrive by itself the first time
    that tool is used, the same way its weights already download on first
    use - switching engine in config.json is enough, no re-bootstrap.

    An environment that exists but was built from an older entry is brought
    up to date, and a failure there is only a warning: a machine that is
    offline must still be able to use a tool that already works."""
    spec = tool_spec(name)
    venv_dir = spec.venv_dir if spec else TOOLS_DIR / f"venv-{name}"
    existing = venv_python(venv_dir)

    if spec is None:
        # Not in the registry: a tool whose entry was deleted, or a typo. Use
        # whatever is on disk rather than refusing, and say which it was.
        if existing:
            return existing
        raise FileNotFoundError(
            f"'{name}' is not one of remanga's tools ({', '.join(TOOL_NAMES)}), "
            f"and {venv_dir} does not exist."
        )

    if existing and is_current(spec):
        backfill_marker(spec, default_torch_backend())
        return existing

    if existing:
        say(f"{spec.display_name}'s environment is out of date - updating it...")
        if not install_tool(spec):
            warn(f"could not update {spec.display_name}'s environment - carrying on with the "
                 f"one already installed. `./run.sh setup-tools --tool {spec.name}` retries it.")
        return venv_python(venv_dir) or existing

    say(f"{spec.display_name} has no environment yet - installing it now. "
        f"This happens once, and downloads a few GB.")
    if not install_tool(spec):
        raise RuntimeError(
            f"could not install {spec.display_name}'s environment ({venv_dir}). "
            f"Retry with `./run.sh setup-tools --tool {spec.name}`."
        )
    python = venv_python(venv_dir)
    if python is None:
        raise FileNotFoundError(f"{spec.display_name}'s environment installed but has no interpreter: {venv_dir}")
    return python


def provision(names: list[str] | None = None, torch_backend: str | None = None,
              *, force: bool = False) -> list[str]:
    """Installs/updates every named tool (all of them by default). Returns
    the names that failed, for the caller's own summary."""
    backend = torch_backend or default_torch_backend()
    wanted = [spec for spec in TOOLS if not names or spec.name in names]
    unknown = [name for name in (names or []) if tool_spec(name) is None]
    for name in unknown:
        warn(f"no tool called '{name}' - known tools: {', '.join(TOOL_NAMES)}")

    failed = list(unknown)
    for spec in wanted:
        if not force and venv_python(spec.venv_dir) and is_current(spec):
            say(f"{spec.display_name} environment is already up to date.")
            continue
        if not install_tool(spec, backend, force=force):
            failed.append(spec.name)
    return failed


def orphan_envs() -> list[Path]:
    """`.tools/venv-*` directories no tool claims any more - what a removed
    TOOLS entry leaves behind. Reported rather than deleted: several GB that
    somebody may still want is not this function's call to make."""
    if not TOOLS_DIR.is_dir():
        return []
    known = {f"venv-{name}" for name in TOOL_NAMES}
    return sorted(p for p in TOOLS_DIR.glob("venv-*") if p.is_dir() and p.name not in known)


def status_rows() -> list[tuple[str, str, str]]:
    """(name, display name, state) for every tool, for the setup screens."""
    rows = []
    for spec in TOOLS:
        if not venv_python(spec.venv_dir):
            state = "not installed"
        elif is_current(spec):
            state = "ready"
        else:
            state = "needs updating"
        rows.append((spec.name, spec.display_name, state))
    return rows
