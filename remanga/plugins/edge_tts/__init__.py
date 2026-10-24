"""Microsoft Edge's online neural voices (the Read Aloud voices: Guy, Andrew,
Brian, Aria, ...), through the edge-tts package. No model, no GPU: the text is
read by Microsoft's service, so it needs the internet, and that service is
Edge's read-aloud feature, not a licensed API - see the README.

    config.py   its settings block (tts.edge in config.json) and the voices
    synth.py    the Synthesizer driving the worker
    rows.py     its rows on the Settings screen
    scripts/    the worker, run in .tools/venv-edge-tts
    setup.py    its environment - runs on its own too"""

from remanga.plugins import TTSEngine, register
from remanga.plugins.edge_tts.setup import TOOL

register("tool", TOOL)   # setup.py: its environment (no weights)

register("tts", TTSEngine(
    "edge", "Edge voices",
    "Microsoft Edge's online neural voices (Guy, Andrew, Brian...) - needs internet",
    tool_name="edge-tts",
    config="remanga.plugins.edge_tts.config:EdgeConfig",
    synthesizer="remanga.plugins.edge_tts.synth:EdgeSynthesizer",
    settings_rows="remanga.plugins.edge_tts.rows:edge_rows",
    order=17,
))
