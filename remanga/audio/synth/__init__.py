"""Low-level speech synthesis, one module per supported TTS engine.

Each engine spawns and talks to its own isolated `.tools/venv-<tool>` worker
process (remanga/audio/scripts/*_worker.py) so no two engines' dependency
pins ever have to share a Python process or a dependency resolution - with
each other, or with MAGI v3's environment. See remanga/venvs.py for how
those environments are located.

    base.py     - the worker lifecycle every engine shares
    indextts.py - IndexTTS-2.5
    audio8.py   - Audio8-TTS-Preview-0.1b

`create_synthesizer` below is the only place an engine *name* is mapped to
an engine *class*; everything else asks config.TTSConfig.spec for the
engine's properties (see remanga/config/tts.py)."""

from __future__ import annotations

from typing import Callable, Dict

from remanga.audio.synth.audio8 import Audio8Synthesizer
from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.audio.synth.indextts import IndexTTSSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.config.tts import TTS_ENGINE_SPECS

# engine name -> the class that drives it, keyed by each class's own spec so
# the name isn't written out a second time. Checked against the full spec
# list at import time below, so adding an engine to the specs without a
# driver - or the reverse - fails loudly here rather than at synthesis time,
# deep inside a chapter's TTS run.
ENGINE_CLASSES = (IndexTTSSynthesizer, Audio8Synthesizer)

SYNTHESIZER_BY_ENGINE: Dict[str, Callable[..., BaseWorkerSynthesizer]] = {
    cls.spec.name: cls for cls in ENGINE_CLASSES
}

_missing = {spec.name for spec in TTS_ENGINE_SPECS} ^ set(SYNTHESIZER_BY_ENGINE)
if _missing:  # pragma: no cover - a wiring mistake, not a runtime condition
    raise ImportError(
        f"TTS engine specs and synthesizer classes disagree about: {', '.join(sorted(_missing))}. "
        f"Every engine in remanga.config.tts.TTS_ENGINE_SPECS needs a class here, and vice versa."
    )


def create_synthesizer(tts_config: TTSConfig, audio_config: AudioConfig) -> BaseWorkerSynthesizer:
    """The Synthesizer matching `tts_config.engine`. An unrecognized engine
    name falls back to the default engine, the same way TTSConfig.spec does -
    config.json is hand-editable, and a typo there should degrade rather
    than crash."""
    spec = tts_config.spec
    return SYNTHESIZER_BY_ENGINE[spec.name](tts_config, audio_config)


__all__ = [
    "Audio8Synthesizer",
    "BaseWorkerSynthesizer",
    "IndexTTSSynthesizer",
    "SYNTHESIZER_BY_ENGINE",
    "create_synthesizer",
]
