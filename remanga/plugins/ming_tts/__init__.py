"""Ming-3.0-tts-0.5B (Ant Group, MIT): five built-in English voices, read with
no reference recording and no cloning.

    config.py   its settings block (tts.ming in config.json) and the voices
    synth.py    the Synthesizer driving the worker
    rows.py     its rows on the Settings screen
    scripts/    the worker and the weight download, run in .tools/venv-ming-tts
    setup.py    its environment, its source and its weights - runs on its own too"""

from remanga.plugins import TTSEngine, register
from remanga.plugins.ming_tts.setup import TOOL

register("tool", TOOL)   # setup.py: its environment, source and weights

register("tts", TTSEngine(
    "ming", "Ming-3.0-tts",
    "Five built-in English voices - newer than Kokoro, slower",
    tool_name="ming-tts",
    config="remanga.plugins.ming_tts.config:MingConfig",
    synthesizer="remanga.plugins.ming_tts.synth:MingSynthesizer",
    settings_rows="remanga.plugins.ming_tts.rows:ming_rows",
    order=15,
))
