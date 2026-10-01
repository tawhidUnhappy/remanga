"""Kokoro-82M's rows on the Settings screen: the voice and the speed. See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.kokoro.voices import KOKORO_VOICES
from remanga.ui.dialogs import Ask, Choice, number_check
from remanga.ui.voice_rows import Row, wait_for


async def _pick_kokoro_voice(screen, config: RemangaConfig) -> None:
    voice = await wait_for(screen)(Choice(
        "Narrator voice", [(v.label, f"grade {v.grade} · {v.accent}", v.name) for v in KOKORO_VOICES],
        current=config.tts.kokoro.voice,
        note="Kokoro-82M's own voices, best graded first. A new voice narrates chapters again."))
    if voice:
        config.tts.kokoro.voice = voice


async def _set_kokoro_speed(screen, config: RemangaConfig) -> None:
    speed = await wait_for(screen)(Ask(
        "Speaking speed", "Speed (1.0 is normal)", value=f"{config.tts.kokoro.speed:g}",
        check=number_check(0.5, 2.0),
        note="1.0 is the voice's own pace, about 185 words a minute. Past about 1.35 Kokoro starts "
             "dropping the pauses between sentences. Changing this narrates every chapter again."))
    if speed is not None:
        config.tts.kokoro.speed = float(speed)


def kokoro_rows(config: RemangaConfig) -> list[Row]:
    kokoro = config.tts.kokoro
    return [
        Row("Narrator voice", kokoro.voice_label, _pick_kokoro_voice, "the voice that reads every panel",
            keys=("tts.kokoro.voice",)),
        Row("Speaking speed", f"{kokoro.speed:g}x", _set_kokoro_speed, "how fast it talks (1 = normal)",
            keys=("tts.kokoro.speed",)),
    ]
