"""Kokoro-82M's rows on the Settings screen: the voice, and the speed (locked). See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.kokoro.config import SPEED
from remanga.plugins.kokoro.voices import KOKORO_VOICES, marked_label
from remanga.ui.dialogs import Choice
from remanga.ui.voice_rows import Row, wait_for


async def _pick_kokoro_voice(screen, config: RemangaConfig) -> None:
    voice = await wait_for(screen)(Choice(
        "Narrator voice", [(marked_label(v), f"grade {v.grade} · {v.accent}", v.name) for v in KOKORO_VOICES],
        current=config.tts.kokoro.voice,
        note="Kokoro-82M's own voices, best graded first - ★ marks the best one. A new voice narrates chapters again."))
    if voice:
        config.tts.kokoro.voice = voice


async def _speed_locked(screen, config: RemangaConfig) -> None:
    screen.notify(f"Speaking speed is a fixed preset ({SPEED:g}x, YouTube/TikTok pacing) - it can't be changed "
                  f"here.", timeout=6)


def kokoro_rows(config: RemangaConfig) -> list[Row]:
    kokoro = config.tts.kokoro
    return [
        Row("Narrator voice", kokoro.voice_label, _pick_kokoro_voice, "the voice that reads every panel",
            keys=("tts.kokoro.voice",)),
        Row("Speaking speed", f"{SPEED:g}x  (locked)", _speed_locked, "fixed preset: YouTube/TikTok pacing"),
    ]
