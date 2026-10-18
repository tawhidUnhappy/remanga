"""Kokoro-82M's rows on the Settings screen: the voice and the speed. See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.kokoro.voices import KOKORO_VOICES, marked_label
from remanga.ui.dialogs import Ask, Choice, number_check
from remanga.ui.voice_rows import Row, wait_for


async def _pick_kokoro_voice(screen, config: RemangaConfig) -> None:
    voice = await wait_for(screen)(Choice(
        "Narrator voice", [(marked_label(v), f"grade {v.grade} · {v.accent}", v.name) for v in KOKORO_VOICES],
        current=config.tts.kokoro.voice,
        note="Kokoro-82M's own voices, best graded first - ★ marks the best one. A new voice narrates chapters again."))
    if voice:
        config.tts.kokoro.voice = voice


# Speaking speeds offered in the list; any other is typed in as Custom.
SPEEDS = ((1.0, "off - the voice's own pace, about 185 words a minute"),
          (1.05, "a touch quicker"),
          (1.08, "YouTube/TikTok pacing - recommended"),
          (1.1, "brisk"),
          (1.12, "urgent - the top of the pacing range"))


def speed_label(speed: float) -> str:
    return "off (1x)" if speed == 1.0 else f"{speed:g}x"


async def _set_kokoro_speed(screen, config: RemangaConfig) -> None:
    kokoro = config.tts.kokoro
    options = [(speed_label(s), hint, s) for s, hint in SPEEDS]
    if all(kokoro.speed != s for s, _ in SPEEDS):
        options.append((speed_label(kokoro.speed), "your custom speed", kokoro.speed))
    options.append(("Custom...", "type your own speed", "custom"))
    note = ("A faster read adds urgency - default TTS pace is slow for YouTube and TikTok. Past about "
            "1.35 Kokoro starts dropping the pauses between sentences. Changing this narrates every "
            "chapter again.")
    speed = await wait_for(screen)(Choice("Speaking speed", options, current=kokoro.speed, note=note))
    if speed == "custom":
        speed = await wait_for(screen)(Ask(
            "Speaking speed", "Speed (1.0 is normal)", value=f"{kokoro.speed:g}",
            check=number_check(0.5, 2.0), note=note))
    if speed is not None:
        kokoro.speed = float(speed)


def kokoro_rows(config: RemangaConfig) -> list[Row]:
    kokoro = config.tts.kokoro
    return [
        Row("Narrator voice", kokoro.voice_label, _pick_kokoro_voice, "the voice that reads every panel",
            keys=("tts.kokoro.voice",)),
        Row("Speaking speed", speed_label(kokoro.speed), _set_kokoro_speed, "speed-up for YouTube pacing (1.05-1.12)",
            keys=("tts.kokoro.speed",)),
    ]
