"""Fish Audio Drama 3 (35B MoE, 3B active; Fish Audio Community License 1.0 -
built with Fish Audio): the #1 open-weights voice on Artificial Analysis's
TTS leaderboard in October 2026. Run through speech.cpp's Q4_K port, on
Vulkan, with the experts the 12 GB GPU cannot hold computed on the CPU. Its
voice is described in words, not cloned.

    config.py   its settings block (tts.drama3 in config.json) and the voices
    synth.py    the Synthesizer driving the worker, and the model file
    rows.py     its rows on the Settings screen
    scripts/    the worker (stdlib only), run in .tools/venv-drama3
    setup.py    its environment, speech.cpp and the model - runs on its own too"""

from remanga.plugins import TTSEngine, register
from remanga.plugins.drama3.setup import TOOL

register("tool", TOOL)   # setup.py: its environment, speech.cpp and the model

register("tts", TTSEngine(
    "drama3", "Fish Audio Drama 3",
    "Best quality - a natural narrator, the same every chapter; slow (a 16-min chapter ~26 min on an RTX 3060), 21 GB",
    tool_name="drama3",
    config="remanga.plugins.drama3.config:Drama3Config",
    synthesizer="remanga.plugins.drama3.synth:Drama3Synthesizer",
    settings_rows="remanga.plugins.drama3.rows:drama3_rows",
    fits="remanga.plugins.drama3.fit:fits",
    recommend="remanga.plugins.drama3.fit:recommend",
    quality=30,
    order=16,
))
