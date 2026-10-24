"""Ming-3.0-tts's row on the Settings screen: the voice. See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.ming_tts.config import MING_VOICES
from remanga.ui.dialogs import Choice
from remanga.ui.voice_rows import Row, wait_for


async def _pick_ming_voice(screen, config: RemangaConfig) -> None:
    voice = await wait_for(screen)(Choice(
        "Narrator voice", [(v.label, f"{v.accent} · {v.use}", v.name) for v in MING_VOICES],
        current=config.tts.ming.spec.name,
        note="Ming-3.0-tts's built-in English voices. A new voice narrates chapters again."))
    if voice:
        config.tts.ming.voice = voice


def ming_rows(config: RemangaConfig) -> list[Row]:
    return [
        Row("Narrator voice", config.tts.ming.voice_label, _pick_ming_voice, "the voice that reads every panel",
            keys=("tts.ming.voice",)),
    ]
