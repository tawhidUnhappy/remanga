"""Speech synthesis: one Synthesizer per engine, each driving its own isolated
venv worker (remanga/audio/scripts/).

    base.py     the worker lifecycle and text chunking every engine shares
    kokoro.py   Kokoro-82M - fixed voices
    qwen.py     Qwen3-TTS - preset narrators, or a voice designed from words

Adding an engine: a Synthesizer here and its name in SYNTHESIZERS, plus the
three pieces named in config/tts_engines.py. Nothing else in the pipeline asks
which engine is running - see create_synthesizer."""

from __future__ import annotations

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.audio.synth.kokoro import KokoroSynthesizer
from remanga.audio.synth.qwen import QwenSynthesizer
from remanga.config import AudioConfig, TTSConfig

SYNTHESIZERS: dict[str, type[BaseWorkerSynthesizer]] = {
    "kokoro": KokoroSynthesizer,
    "qwen": QwenSynthesizer,
}


def create_synthesizer(tts_config: TTSConfig, audio_config: AudioConfig) -> BaseWorkerSynthesizer:
    """The synthesizer for the configured engine, falling back to the default
    engine for a name nothing implements (config.json is hand-editable)."""
    engine = SYNTHESIZERS.get(tts_config.spec.name) or SYNTHESIZERS[tts_config.__class__().spec.name]
    return engine(tts_config, audio_config)


__all__ = ["SYNTHESIZERS", "BaseWorkerSynthesizer", "KokoroSynthesizer", "QwenSynthesizer", "create_synthesizer"]
