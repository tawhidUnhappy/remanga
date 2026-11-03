"""Kokoro-82M's setup: its isolated environment (.tools/venv-kokoro) and its weights.

remanga runs this the first time Kokoro-82M is used, from bootstrap.sh and
from `./run.sh setup --tool kokoro`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.kokoro.setup [--force] [--torch-backend cu129] [--no-weights]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

TOOL = ToolSpec(
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
    install="remanga.plugins.kokoro.setup:install",
    weights="remanga.plugins.kokoro.setup:weights",
)


def install(torch_backend: str | None = None, force: bool = False) -> bool:
    """The environment: TOOL.steps installed with uv into .tools/venv-kokoro."""
    from remanga.tool_envs import build_env

    return build_env(TOOL, torch_backend, force=force)


def weights(config) -> None:
    """The model and every voice pack (see scripts/download_kokoro.py)."""
    from remanga.plugins.kokoro.synth import model_manager

    model_manager(config.tts.kokoro).ensure_model()


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
