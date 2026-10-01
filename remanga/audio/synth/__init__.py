"""Speech synthesis: the worker lifecycle every engine shares (base.py), and
building the configured engine's Synthesizer.

The engines themselves are plug-ins (remanga/plugins/, kind "tts"), each with
its Synthesizer and worker script in its own folder. Nothing else in the
pipeline asks which engine is running - see create_synthesizer."""

from __future__ import annotations

from remanga import plugins
from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig


def create_synthesizer(tts_config: TTSConfig, audio_config: AudioConfig) -> BaseWorkerSynthesizer:
    """The synthesizer for the configured engine - the default engine for a
    name nothing implements (config.json is hand-editable)."""
    return plugins.resolve(tts_config.spec.synthesizer)(tts_config, audio_config)


__all__ = ["BaseWorkerSynthesizer", "create_synthesizer"]
