"""Edge voices' setup: its isolated environment (.tools/venv-edge-tts). There
are no weights - the voices are Microsoft's online service.

remanga runs this the first time the engine is used, from bootstrap.sh and
from `./run.sh setup --tool edge-tts`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.edge_tts.setup [--force]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

TOOL = ToolSpec(
    "edge-tts", "Edge voices", "TTS engine - Microsoft Edge's online neural voices",
    steps=(InstallStep(("edge-tts==7.3.*",), torch_backend=False),),
)


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
