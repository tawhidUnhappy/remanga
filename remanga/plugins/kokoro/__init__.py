"""Kokoro-82M: fixed, named studio voices - fast, and the same every time.

    config.py   its settings block (tts.kokoro in config.json)
    voices.py   the voice catalogue
    synth.py    the Synthesizer driving the worker
    rows.py     its rows on the Settings screen
    scripts/    the worker and the weight download, run in .tools/venv-kokoro
    setup.py    its environment and weights - runs on its own too"""

from remanga.plugins import TTSEngine, register
from remanga.plugins.kokoro.setup import TOOL

register("tool", TOOL)   # setup.py: its environment and weights

# First in order: the default engine, and the fallback for a name config.json
# doesn't know.
register("tts", TTSEngine(
    "kokoro", "Kokoro-82M", "Fixed studio voices - fast, and the same every time",
    tool_name="kokoro",
    config="remanga.plugins.kokoro.config:KokoroConfig",
    synthesizer="remanga.plugins.kokoro.synth:KokoroSynthesizer",
    settings_rows="remanga.plugins.kokoro.rows:kokoro_rows",
    order=10,
))
