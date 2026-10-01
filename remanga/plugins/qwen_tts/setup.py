"""Qwen3-TTS's setup: its isolated environment (.tools/venv-qwen-tts) and the weights its voice needs.

remanga runs this the first time Qwen3-TTS is used, from bootstrap.sh and
from `./run.sh setup --tool qwen-tts`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.qwen_tts.setup [--force] [--torch-backend cu129] [--no-weights]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

TOOL = ToolSpec(
    "qwen-tts", "Qwen3-TTS", "TTS engine - voices designed from a description, and preset narrators",
    steps=(
        # qwen-tts pulls transformers and its own tokenizer stack; torch
        # comes from this machine's wheel index (see hardware.py), which
        # is why it is named first rather than left to the dependency
        # resolver. flash-attn is deliberately left out: it builds from
        # source for many minutes and only saves some VRAM.
        InstallStep(("torch", "torchaudio", "qwen-tts", "soundfile", "huggingface-hub")),
    ),
    install="remanga.plugins.qwen_tts.setup:install",
    weights="remanga.plugins.qwen_tts.setup:weights",
)


def install(torch_backend: str | None = None, force: bool = False) -> bool:
    """The environment: TOOL.steps installed with uv into .tools/venv-qwen-tts."""
    from remanga.tool_envs import build_env

    return build_env(TOOL, torch_backend, force=force)


def weights(config) -> None:
    """The model variant the configured voice uses - a cloned/designed voice
    the Base model, a preset the CustomVoice one. The VoiceDesign model is
    fetched only when a voice is designed."""
    from remanga.plugins.qwen_tts.synth import model_manager

    qwen = config.tts.qwen
    model_manager(qwen, "clone" if qwen.designed else "custom").ensure_model()


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
