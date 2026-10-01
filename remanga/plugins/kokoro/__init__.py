"""Kokoro-82M: fixed, named studio voices - fast, and the same every time.

    config.py   its settings block (tts.kokoro in config.json)
    voices.py   the voice catalogue
    synth.py    the Synthesizer driving the worker
    rows.py     its rows on the Settings screen
    scripts/    the worker and the weight download, run in .tools/venv-kokoro"""

from remanga.plugins import TTSEngine, register
from remanga.tool_envs.spec import InstallStep, ToolSpec

register("tool", ToolSpec(
    "kokoro", "Kokoro-82M", "TTS engine - fixed built-in voices",
    steps=(
        InstallStep(("torch", "kokoro", "soundfile", "numpy", "huggingface-hub")),
        # misaki (Kokoro's English G2P, pulled in above) loads a spaCy
        # pipeline, and spaCy ships its models as separate packages rather
        # than fetching them at runtime - without this every synthesis dies
        # on "Can't find model 'en_core_web_sm'".
        #
        # Installed from the release URL rather than via `python -m spacy
        # download`: that command shells out to the ambient installer,
        # which under uv reports "Download and installation successful"
        # and installs NOTHING into the target venv. Verified - it exits 0
        # and the model is still absent. The URL form is the only one that
        # reliably lands here. No torch in it, so no wheel index needed.
        InstallStep(
            ("https://github.com/explosion/spacy-models/releases/download/"
             "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",),
            torch_backend=False,
        ),
    ),
))

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
