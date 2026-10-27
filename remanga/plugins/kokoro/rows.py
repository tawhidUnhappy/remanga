"""Kokoro-82M's row on the Settings screen: the voice, read at its own pace (no
speed row since 2026-10-27 - the user wants every voice raw, never sped up). See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
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


def kokoro_rows(config: RemangaConfig) -> list[Row]:
    kokoro = config.tts.kokoro
    return [
        Row("Narrator voice", kokoro.voice_label, _pick_kokoro_voice, "the voice that reads every panel",
            keys=("tts.kokoro.voice",)),
    ]
