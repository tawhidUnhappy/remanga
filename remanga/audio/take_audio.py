"""A take as the engine wrote it, and what the takes on disk were made with.

The narrator's audio is never edited: no pause is cut, nothing is added -
the take is only brought to the project's sample rate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga.audio.resample import load_audio
from remanga.config import AudioConfig, TTSConfig


def load_take(raw: Path, audio_config: AudioConfig) -> AudioSegment:
    """A take as the engine wrote it, at the project's rate."""
    return load_audio(raw, audio_config.sample_rate, channels=1)


def narration_identity(tts_config: TTSConfig, audio_config: AudioConfig) -> dict[str, Any]:
    """What the takes on disk were made with: the engine and its voice."""
    return tts_config.identity()
