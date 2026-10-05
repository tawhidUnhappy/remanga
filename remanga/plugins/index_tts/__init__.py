"""IndexTTS-2.5: clones the voice of any recording from its first 15 seconds,
no transcript needed - steadier than Qwen's clone, slower than Kokoro.

    config.py   its settings block (tts.index_tts in config.json)
    synth.py    the Synthesizer driving the worker
    rows.py     its rows on the Settings screen
    scripts/    the worker and the weight download, run in .tools/venv-index-tts
    setup.py    its environment and weights - runs on its own too"""

from remanga.plugins import TTSEngine, register
from remanga.plugins.index_tts.setup import TOOL

register("tool", TOOL)   # setup.py: its environment and weights

register("tts", TTSEngine(
    "index_tts", "IndexTTS-2.5",
    "Clones the voice of a recording in global/voice/ - no transcript needed",
    tool_name="index-tts",
    config="remanga.plugins.index_tts.config:IndexTTSConfig",
    synthesizer="remanga.plugins.index_tts.synth:IndexTTSSynthesizer",
    settings_rows="remanga.plugins.index_tts.rows:index_tts_rows",
    clones_voice=True,
    order=30,
))
