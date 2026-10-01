"""faster-whisper: reads word timings back off narrated audio - how a batched
narration finds each panel in its take, and what a cloned voice's reference
recording says. Runs in .tools/venv-faster-whisper.

    transcribe.py   the Transcriber (worker driver)
    scripts/        the worker and the weight download
    setup.py        its environment and weights - runs on its own too"""

from remanga.plugins import register
from remanga.plugins.faster_whisper.setup import TOOL

register("tool", TOOL)   # setup.py: its environment and weights
