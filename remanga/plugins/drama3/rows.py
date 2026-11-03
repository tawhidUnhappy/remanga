"""Fish Audio Drama 3's row on the Settings screen: the voice. See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.drama3.config import DRAMA_VOICES
from remanga.ui.dialogs import Choice
from remanga.ui.voice_rows import Row, wait_for


async def _pick_drama_voice(screen, config: RemangaConfig) -> None:
    voice = await wait_for(screen)(Choice(
        "Narrator voice", [(v.label, v.use, v.name) for v in DRAMA_VOICES],
        current=config.tts.drama3.spec.name,
        note="Drama 3 has no named voices: it makes one from this description and the seed "
             "(tts.drama3.seed). A new voice narrates chapters again."))
    if voice:
        config.tts.drama3.voice = voice


def drama3_rows(config: RemangaConfig) -> list[Row]:
    return [
        Row("Narrator voice", config.tts.drama3.voice_label, _pick_drama_voice, "the voice that reads every panel",
            keys=("tts.drama3.voice",)),
    ]
