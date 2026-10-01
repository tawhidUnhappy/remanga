"""MAGI v3's setup: its isolated environment (.tools/venv-magi) and its weights.

remanga runs this the first time MAGI v3 is used, from bootstrap.sh and
from `./run.sh setup --tool magi`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.magi.setup [--force] [--torch-backend cu129] [--no-weights]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

TOOL = ToolSpec(
    "magi", "MAGI v3", "panel detection for the Panel Marker web UI",
    steps=(
        # einops/matplotlib: undeclared imports MAGI v3's remote modeling
        # code needs beyond its own requirements. assist.py auto-installs
        # anything still missing on first load; listing the known ones saves
        # a round trip.
        InstallStep((
            "torch", "transformers<4.52.0", "timm", "shapely",
            "pytorch-metric-learning", "huggingface-hub", "pillow", "numpy",
            "einops", "matplotlib",
        )),
    ),
    install="remanga.plugins.magi.setup:install",
    weights="remanga.plugins.magi.setup:weights",
)


def install(torch_backend: str | None = None, force: bool = False) -> bool:
    """The environment: TOOL.steps installed with uv into .tools/venv-magi."""
    from remanga.tool_envs import build_env

    return build_env(TOOL, torch_backend, force=force)


def weights(config) -> None:
    """The weights, then one load-and-release pass so the Panel Marker's
    detection is ready the first time it is asked (see assist.py)."""
    from remanga.plugins.magi.assist import ensure_weights_downloaded

    ensure_weights_downloaded(config.marker)


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
