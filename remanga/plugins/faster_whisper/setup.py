"""faster-whisper's setup: its isolated environment (.tools/venv-faster-whisper) and its weights.

remanga runs this the first time faster-whisper is used, from bootstrap.sh and
from `./run.sh setup --tool faster-whisper`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.faster_whisper.setup [--force] [--torch-backend cu129] [--no-weights]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

TOOL = ToolSpec(
    "faster-whisper", "faster-whisper", "word timestamps for a batched narration",
    steps=(
        # CTranslate2, not torch, so this machine's wheel index has no
        # business here - hence torch_backend=False, the only entry that
        # sets it on its first step.
        #
        # The two NVIDIA runtime libraries are named because ctranslate2
        # dlopens cuDNN and cuBLAS at run time and does not declare them
        # as dependencies: without them the model loads and then dies on
        # "Unable to load libcudnn_ops.so" the first time it is asked for
        # anything, which reads as a model problem and is not one.
        InstallStep(("faster-whisper", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"),
                    torch_backend=False),
    ),
    install="remanga.plugins.faster_whisper.setup:install",
    weights="remanga.plugins.faster_whisper.setup:weights",
)


def install(torch_backend: str | None = None, force: bool = False) -> bool:
    """The environment: TOOL.steps installed with uv into .tools/venv-faster-whisper."""
    from remanga.tool_envs import build_env

    return build_env(TOOL, torch_backend, force=force)


def weights(config) -> None:
    """The model subtitles.model_dir names (large-v3 by default)."""
    from remanga.plugins.faster_whisper.transcribe import Transcriber

    Transcriber(config.subtitles).model_manager.ensure_model()


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
