"""Speech synthesis: Kokoro-82M, driven through its own isolated
`.tools/venv-kokoro` worker process (remanga/audio/scripts/kokoro_worker.py).

    base.py    - the worker lifecycle
    kokoro.py  - Kokoro-82M"""

from __future__ import annotations

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.audio.synth.kokoro import KokoroSynthesizer
from remanga.config import AudioConfig, TTSConfig


def create_synthesizer(tts_config: TTSConfig, audio_config: AudioConfig) -> KokoroSynthesizer:
    return KokoroSynthesizer(tts_config, audio_config)


__all__ = ["BaseWorkerSynthesizer", "KokoroSynthesizer", "create_synthesizer"]
