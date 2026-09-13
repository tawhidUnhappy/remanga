#!/usr/bin/env python3
"""Every isolated tool environment remanga provisions, and how.

Each heavy ML tool runs in its own `.tools/venv-<name>` (see
remanga/paths/tools.py) because their dependency pins genuinely conflict -
MAGI v3 needs transformers<4.52, DeepSeek-OCR-2 pins ==4.46.3, Chatterbox
pins ==5.2.0, and nothing guarantees any two of them would ever agree on one
resolution.

This module is the single description of those environments: what each one
is called, what goes into it, and why. It is what bootstrap.sh provisions
from, what `remanga setup-tools` repairs from, and what a tool installs
itself from the first time it is used (remanga/venvs.py:get_tool_python).

Adding a tool is a TOOLS entry plus the code that drives it; removing one is
deleting both. Nothing else in the tree hand-writes a venv path, an install
command or a package list, so neither direction can leave half a tool behind
in a shell script nobody reads. Before this existed, adding one meant
editing a block of bootstrap.sh by hand, and removing one meant remembering
that block was there.

Stdlib only, and runnable as a script (`python remanga/tool_envs.py
install`) as well as importable - bootstrap.sh calls it before remanga's own
environment exists, exactly like remanga/hardware.py.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / ".tools"
PYTHON_VERSION = "3.11"

# Written into an environment once its install finishes, so a later run can
# tell "up to date with its TOOLS entry" from "half-installed, or built from
# an older entry". Changing an entry - a new package, a different pin -
# therefore re-syncs that environment the next time it is used, instead of
# waiting for somebody to think of re-running bootstrap.
MARKER_NAME = ".remanga-tool.json"


def say(message: str) -> None:
    print(f"[+] {message}", flush=True)


def warn(message: str) -> None:
    print(f"[-] {message}", file=sys.stderr, flush=True)


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


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "kokoro", "Kokoro-82M", "TTS engine - fixed built-in voices",
        steps=(
            InstallStep(("torch", "kokoro", "soundfile", "numpy", "huggingface-hub")),
            # misaki (Kokoro's English G2P, pulled in above) loads a spaCy
            # pipeline, and spaCy ships its models as separate packages rather
            # than fetching them at runtime - without this every synthesis dies
            # on "Can't find model 'en_core_web_sm'".
            #
            # Installed from the release URL rather than via `python -m spacy
            # download`: that command shells out to the ambient installer,
            # which under uv reports "Download and installation successful"
            # and installs NOTHING into the target venv. Verified - it exits 0
            # and the model is still absent. The URL form is the only one that
            # reliably lands here. No torch in it, so no wheel index needed.
            InstallStep(
                ("https://github.com/explosion/spacy-models/releases/download/"
                 "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",),
                torch_backend=False,
            ),
        ),
    ),
    ToolSpec(
        "chatterbox", "Chatterbox Turbo", "TTS engine - clones a narrator from a recording",
        steps=(
            # chatterbox-tts pins torch==2.6.0 exactly, which makes a plain
            # install unsatisfiable on every machine that resolves to a recent
            # wheel index: 2.6 is not in cu129 at all (it jumps from <2.6 to
            # >2.7), and uv says so - "there is no version of torch==2.6.0".
            # Like DeepSeek-OCR-2's torch pin it is not load-bearing, so the
            # dependencies go in first against this machine's torch, and the
            # package itself second with --no-deps. transformers and diffusers
            # keep upstream's exact pins - the model code is written against
            # them. Left out on purpose: gradio (upstream's demo UI, several
            # hundred MB) and spacy-pkuseg/pykakasi (Chinese/Japanese text for
            # the multilingual model, imported only inside those code paths).
            InstallStep((
                "torch", "torchaudio", "numpy<2", "librosa==0.11.0", "s3tokenizer",
                "transformers==5.2.0", "diffusers==0.29.0",
                "conformer==0.3.2", "safetensors", "pyloudnorm", "omegaconf",
                "soundfile", "huggingface-hub",
            )),
            # The PyPI package named "resemble-perth" is an abstract-base-class
            # stub with no working implementation - `PerthImplicitWatermarker`
            # imports as None from it, which fails with an opaque "'NoneType'
            # object is not callable" the instant a worker tries to construct
            # one. chatterbox-tts's own pyproject.toml pins the real
            # implementation from GitHub instead of PyPI for exactly this
            # reason; installed here the same way, before the --no-deps
            # package below would otherwise pull in the broken PyPI one.
            InstallStep(
                ("resemble-perth @ git+https://github.com/resemble-ai/Perth.git@master",),
                torch_backend=False,
            ),
            InstallStep(("chatterbox-tts==0.1.7",), torch_backend=False, no_deps=True),
        ),
    ),
    ToolSpec(
        "magi", "MAGI v3", "panel detection for the Panel Marker web UI",
        steps=(
            # einops/matplotlib: undeclared imports MAGI v3's remote modeling
            # code needs beyond its own requirements. magi_assist.py
            # auto-installs anything still missing on first load; listing the
            # known ones saves a round trip.
            InstallStep((
                "torch", "transformers<4.52.0", "timm", "shapely",
                "pytorch-metric-learning", "huggingface-hub", "pillow", "numpy",
                "einops", "matplotlib",
            )),
        ),
    ),
    ToolSpec(
        "deepseek-ocr", "DeepSeek-OCR-2", "OCR for the Narration Writer's per-panel button",
        steps=(
            # transformers is pinned exactly, torch is not. The model card pins
            # both (transformers==4.46.3, torch==2.6.0), but the pins are not
            # equally load-bearing: the pinned transformers is what the model's
            # own trust_remote_code modeling code is written against, while
            # torch 2.6 simply is not in the wheel index this machine resolves
            # to, so honouring it would mean installing wheels built for a
            # different machine. einops/addict/easydict are undeclared imports
            # that modeling code needs.
            #
            # flash-attn is deliberately absent. The card uses it, but it is a
            # long, fragile CUDA extension build and transformers falls back to
            # its own attention without it - the same reasoning that keeps
            # every other optional kernel build out of a first run.
            InstallStep((
                "torch", "transformers==4.46.3", "tokenizers==0.20.3", "einops",
                "addict", "easydict", "accelerate", "pillow", "huggingface-hub",
                "safetensors",
            )),
        ),
    ),
)

TOOL_NAMES = tuple(spec.name for spec in TOOLS)


def tool_spec(name: str) -> ToolSpec | None:
    """The entry for `name`, or None if no tool is called that."""
    for spec in TOOLS:
        if spec.name == name:
            return spec
    return None


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
        sys.path.insert(0, str(Path(__file__).resolve().parent))
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("install", "list"), nargs="?", default="install")
    parser.add_argument("--tool", action="append", default=[],
                        help="only this tool (repeatable); default is every tool")
    parser.add_argument("--torch-backend", default=None,
                        help="wheel index for torch-ecosystem installs (cu129, rocm6.4, cpu, default)")
    parser.add_argument("--force", action="store_true", help="rebuild the environment from scratch")
    parser.add_argument("--prune", action="store_true",
                        help="delete .tools/venv-* directories no tool claims any more")
    args = parser.parse_args()

    if args.action == "list":
        for name, display, state in status_rows():
            print(f"{name:14} {display:20} {state}")
        for path in orphan_envs():
            print(f"{path.name:14} {'(no such tool)':20} orphaned - delete it with --prune")
        return 0

    failed = provision(args.tool or None, args.torch_backend, force=args.force)

    for path in orphan_envs():
        if args.prune:
            say(f"removing {path} - no tool claims it any more")
            shutil.rmtree(path, ignore_errors=True)
        else:
            say(f"{path} belongs to no tool any more - `--prune` deletes it")

    if failed:
        warn(f"tool environment(s) that failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
