"""Speech synthesis: Chatterbox Turbo, driven through its own isolated
`.tools/venv-chatterbox` worker process (remanga/audio/scripts/chatterbox_worker.py).

    base.py        - the worker lifecycle
    chatterbox.py  - Chatterbox Turbo"""

from __future__ import annotations

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.audio.synth.chatterbox import ChatterboxSynthesizer
from remanga.config import AudioConfig, TTSConfig


def create_synthesizer(tts_config: TTSConfig, audio_config: AudioConfig) -> ChatterboxSynthesizer:
    return ChatterboxSynthesizer(tts_config, audio_config)


__all__ = ["BaseWorkerSynthesizer", "ChatterboxSynthesizer", "create_synthesizer"]
