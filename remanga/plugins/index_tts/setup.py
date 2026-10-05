"""IndexTTS-2.5's setup: its isolated environment (.tools/venv-index-tts) and its weights.

remanga runs this the first time IndexTTS-2.5 is used, from bootstrap.sh and
from `./run.sh setup --tool index-tts`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.index_tts.setup [--force] [--torch-backend cu128] [--no-weights]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

# The release this plug-in is written against. Upstream ships no PyPI package
# and its pyproject still says 2.0.0, so the git tag is what pins it.
INDEXTTS_TAG = "v2.5.0"

TOOL = ToolSpec(
    "index-tts", "IndexTTS-2.5", "TTS engine - clones the voice of a recording, no transcript needed",
    steps=(
        # Upstream pins torch 2.8 and gets it from the cu128 index through
        # tool.uv.sources, which a plain install of the package never reads -
        # so torch is named here, pinned, for this machine's wheel index to
        # supply (see hardware.py) instead of the resolver picking PyPI's.
        InstallStep(("torch==2.8.*", "torchaudio==2.8.*",
                     f"indextts @ git+https://github.com/index-tts/index-tts.git@{INDEXTTS_TAG}",
                     "soundfile", "huggingface-hub")),
    ),
    install="remanga.plugins.index_tts.setup:install",
    weights="remanga.plugins.index_tts.setup:weights",
)


def install(torch_backend: str | None = None, force: bool = False) -> bool:
    """The environment: TOOL.steps installed with uv into .tools/venv-index-tts."""
    from remanga.tool_envs import build_env

    return build_env(TOOL, torch_backend, force=force)


def weights(config) -> None:
    """The IndexTTS-2.5 checkpoint and the four models it loads beside it
    (scripts/download_index_tts.py)."""
    from remanga.plugins.index_tts.synth import model_manager

    model_manager(config.tts.index_tts).ensure_model()


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
