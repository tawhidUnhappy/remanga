"""The Setup category: settings, shared assets, and model weights."""

from __future__ import annotations

from remanga.commands.handlers import (
    setup as setup_handlers,
)
from remanga.commands.spec import Command, Param
from remanga.tool_envs import TOOL_NAMES

SETUP_COMMANDS: list[Command] = [
    Command(
        "setup-config",
        "Walkthrough configuration setup (engine, voice, BGM, resolution, vision format, blur)",
        setup_handlers.setup_config,
        category="Setup",
        detail="every setting, each showing its current value - change one or walk through them all",
    ),
    Command(
        "paths",
        "View/edit the shared asset paths (reference voice WAV, BGM file, TTS transcript) in one "
        "place, without the full setup-config walkthrough",
        setup_handlers.paths,
        category="Setup",
        detail="picks from the audio files already in global/ instead of asking you to type a path",
    ),
    Command(
        "hardware",
        "Show the detected GPU/CPU, the PyTorch wheels chosen for it, and the video encoder in use",
        setup_handlers.hardware,
        category="Setup",
        detail="the same detection bootstrap.sh used - check here if a machine didn't get the GPU build",
    ),
    Command(
        "setup-models",
        "Verify and download model weights with SHA-256 verification",
        setup_handlers.setup_models,
        category="Setup",
        detail="fetches only what the current configuration actually uses",
    ),
    Command(
        "setup-tools",
        "Install/update the isolated .tools/venv-<name> environments (see remanga/tool_envs.py)",
        setup_handlers.setup_tools,
        [
            Param("tool", ["--tool"], type="choice", choices=list(TOOL_NAMES), required=False,
                  help="Only this tool - every tool by default",
                  cli_only=True),
            Param("force", ["--force", "-f"], type="bool", required=False, default=False,
                  help="Rebuild from scratch instead of updating in place",
                  cli_only=True),
        ],
        category="Setup",
        detail="normally not needed - each environment installs itself the first time its engine runs",
    ),
]
