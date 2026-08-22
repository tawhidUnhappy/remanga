"""MAGI v3 panel-detection assist for the panel-marking web UI.

MAGI (https://github.com/ragavsachdeva/magi, https://huggingface.co/ragavsachdeva/magiv3)
is a manga-understanding vision-language model from Oxford (Sachdeva & Zisserman)
that localizes panels, characters, text blocks, and speech-bubble tails on a raw
page image. This module only uses its panel detection: it pre-fills every page's
panel boxes so a person only has to adjust them in the web UI, not draw from
scratch (`remanga/webui/server.py` calls `detect_panels_for_pages`).

License note: the magiv3 model card permits "personal, research, non-commercial,
and not-for-profit" use only - fine for running your own chapters through this
tool, not something to bundle into a redistributed commercial product as-is.

Runs entirely inside the isolated `.venv-magi` environment as a subprocess
(remanga/webui/scripts/magi_worker.py) - MAGI's own pinned dependencies (a
`transformers` capped below 4.52 for its DaViT vision encoder, `timm`,
`shapely`, `pytorch_metric_learning`, ...) never have to coexist with anything
else remanga uses, including IndexTTS-2.5's own isolated environment. See
remanga/venvs.py. Requires a CUDA GPU. Only invoked if `marker.magi_enabled` is
true in config, so nothing about this stage costs anything when it's off.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from rich.console import Console

from remanga.config import MarkerConfig
from remanga.venvs import get_scripts_dir, get_tool_python

console = Console()

# transformers' trust_remote_code error looks like: "This modeling file requires
# the following packages that were not found in your environment: foo, bar. Run
# `pip install foo bar`". MAGI's own modeling file can gain a new import in a
# future revision without pyproject.toml being updated to match, so this parses
# that message out of the worker's stderr instead of hardcoding the package list.
_MISSING_PKG_RE = re.compile(
    r"the following packages that were not found in your environment:\s*([^.]+)\.", re.IGNORECASE
)
_MAX_AUTO_HEAL_ATTEMPTS = 5


def is_gpu_available() -> bool:
    """Checks for a CUDA GPU using .venv-magi's own torch install, since the
    main env no longer carries torch at all."""
    try:
        python = get_tool_python("magi")
    except FileNotFoundError:
        return False
    try:
        result = subprocess.run(
            [str(python), "-c", "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)"],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _pip_install_into_magi_env(packages: Set[str]) -> bool:
    """Installs `packages` into `.venv-magi`, preferring this repo's own
    `bin/uv` (that isolated venv has no `pip` module at all)."""
    names = sorted(packages)
    console.print(f"[yellow]Installing missing dependency into .venv-magi: {' '.join(names)}...[/]")

    repo_root = Path(__file__).resolve().parents[2]
    uv_bin = repo_root / "bin" / "uv"
    magi_python = get_tool_python("magi")
    if uv_bin.exists():
        cmd = [str(uv_bin), "pip", "install", "--python", str(magi_python), *names]
    else:
        cmd = [str(magi_python), "-m", "pip", "install", *names]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"[bold red]Failed to install {' '.join(names)} automatically.[/]")
        return False
    console.print(f"[bold green]✓ Installed {' '.join(names)}.[/]")
    return True


def _spawn_worker(config: MarkerConfig) -> subprocess.Popen:
    python = get_tool_python("magi")
    script = get_scripts_dir("webui") / "magi_worker.py"
    cmd = [
        str(python), "-u", str(script),
        "--repo_id", config.magi_repo_id,
        "--model_dir", config.magi_model_dir,
        "--score_threshold", str(config.magi_panel_score_threshold),
    ]
    return subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
    )


def _spawn_worker_with_auto_heal(config: MarkerConfig) -> subprocess.Popen:
    """Spawns the MAGI worker, waits for its startup event, and - if it
    reports a missing trust_remote_code dependency - installs the package(s)
    into `.venv-magi` and retries, up to _MAX_AUTO_HEAL_ATTEMPTS distinct
    packages, instead of raising mid-session over something one pip install
    would have fixed."""
    attempted: Set[str] = set()

    for _ in range(_MAX_AUTO_HEAL_ATTEMPTS + 1):
        with console.status(f"[bold cyan]Loading MAGI v3 ({config.magi_repo_id})...[/]", spinner="dots"):
            proc = _spawn_worker(config)
            first_line = proc.stdout.readline()

        if not first_line:
            stderr = proc.stderr.read()
            raise RuntimeError(f"MAGI v3 worker exited before starting up:\n{stderr}")

        event = json.loads(first_line)
        if event.get("event") == "ready":
            return proc

        error_text = event.get("error", "")
        match = _MISSING_PKG_RE.search(error_text)
        if not match:
            raise RuntimeError(f"MAGI v3 worker failed to load: {error_text}")

        missing = {pkg.strip() for pkg in match.group(1).replace(",", " ").split() if pkg.strip()}
        missing -= attempted
        if not missing:
            raise RuntimeError(f"MAGI v3 worker still fails after installing: {', '.join(sorted(attempted))}")
        attempted |= missing
        if not _pip_install_into_magi_env(missing):
            raise RuntimeError(f"MAGI v3 worker failed to load: {error_text}")
        console.print("[dim]Retrying MAGI v3 load with the newly installed package(s)...[/]")

    raise RuntimeError(f"MAGI v3 worker still fails to load after installing: {', '.join(sorted(attempted))}")


def ensure_weights_downloaded(config: MarkerConfig) -> Optional[Path]:
    """Pre-fetches the MAGI v3 weights via `.venv-magi`'s HF Hub install, then
    does a full load-and-release pass (auto-healing any missing dependency, see
    _spawn_worker_with_auto_heal) so the panel-marking assist is actually ready
    the first time someone opens the web UI, not just downloaded. Called from
    `remanga setup-models` / bootstrap.sh, the same moment IndexTTS-2.5's
    weights are fetched. No-ops (with a note) if MAGI is disabled in config, or
    if `.venv-magi` / a GPU aren't available."""
    if not config.magi_enabled:
        console.print("[dim]MAGI v3 assist is disabled (marker.magi_enabled=false) - skipping weight download.[/]")
        return None

    try:
        python = get_tool_python("magi")
    except FileNotFoundError as e:
        console.print(f"[yellow]{e}[/]")
        return None

    if not is_gpu_available():
        console.print(
            "[yellow]No CUDA GPU detected in .venv-magi - skipping MAGI v3 weight download. "
            "The panel-marking web UI still works without it (mark panels manually).[/]"
        )
        return None

    script = get_scripts_dir("webui") / "download_magi.py"
    model_dir = Path(config.magi_model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    with console.status(f"[bold cyan]Fetching MAGI v3 weights ({config.magi_repo_id})...[/]", spinner="dots"):
        result = subprocess.run([str(python), str(script), str(model_dir.resolve()), config.magi_repo_id], capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[bold red]Error downloading MAGI v3 weights:[/] {result.stderr.strip()}")
        raise RuntimeError(f"MAGI v3 weight download failed: {result.stderr.strip()}")
    console.print(f"[bold green]✓ MAGI v3 weights downloaded:[/] {model_dir}")

    console.print("[cyan]Verifying MAGI v3 loads correctly...[/]")
    proc = _spawn_worker_with_auto_heal(config)
    proc.stdin.close()  # no page paths to send - just confirming it loads
    proc.wait(timeout=60)

    console.print("[bold green]✓ MAGI v3 verified and ready.[/]")
    return model_dir


def detect_panels_for_pages(
    page_paths: List[Path],
    config: MarkerConfig,
    on_page_done=None,
) -> Dict[str, List[List[float]]]:
    """Runs MAGI v3 panel detection over a batch of page images via the
    `.venv-magi` worker subprocess. Returns {page_filename: [[x1, y1, x2, y2],
    ...]} in pixel space. Calls `on_page_done(filename, boxes)` after each page
    if given, so a caller (the web server) can stream progress to the UI
    instead of blocking until the whole chapter finishes.
    """
    proc = _spawn_worker_with_auto_heal(config)
    console.print("[bold green]✓ MAGI v3 loaded.[/]")

    results: Dict[str, List[List[float]]] = {}
    try:
        for path in page_paths:
            proc.stdin.write(str(path.resolve()) + "\n")
        proc.stdin.close()

        for line in proc.stdout:
            event = json.loads(line)
            if "filename" in event and "boxes" in event:
                results[event["filename"]] = event["boxes"]
                if on_page_done:
                    on_page_done(event["filename"], event["boxes"])
            elif event.get("event") == "page_error":
                console.print(f"[yellow]MAGI v3 failed on {event.get('filename')}: {event.get('error')}[/]")
    finally:
        proc.wait(timeout=30)

    return results
