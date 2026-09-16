"""The driver side of every isolated-venv worker: one spawn, one auto-heal,
one request/shutdown lifecycle, shared by TTS (audio/synth/), OCR
(ocr/engine.py) and MAGI (webui/magi_assist.py).

    heal.py     starting a worker, installing what its own install missed
    process.py  ToolWorker: the running process and the requests to it

The worker scripts themselves live in each package's scripts/ and stay
standalone - they run inside the tool's environment, where remanga is not
installed, so they cannot import any of this."""

from __future__ import annotations

from remanga.workers.heal import MAX_AUTO_HEAL_ATTEMPTS, pip_install_into_tool_env, start_worker
from remanga.workers.process import STDERR_TAIL_LINES, ToolWorker, spawn_script_worker

__all__ = [
    "MAX_AUTO_HEAL_ATTEMPTS",
    "STDERR_TAIL_LINES",
    "ToolWorker",
    "pip_install_into_tool_env",
    "spawn_script_worker",
    "start_worker",
]
