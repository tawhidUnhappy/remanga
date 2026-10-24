"""Edge voices' row on the Settings screen: the voice. See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.edge_tts.config import EDGE_VOICES
from remanga.ui.dialogs import Choice
from remanga.ui.voice_rows import Row, wait_for


async def _pick_edge_voice(screen, config: RemangaConfig) -> None:
    voice = await wait_for(screen)(Choice(
        "Narrator voice", [(v.label, v.use, v.name) for v in EDGE_VOICES],
        current=config.tts.edge.spec.name,
        note="Microsoft Edge's US English voices, read online. A new voice narrates chapters again."))
    if voice:
        config.tts.edge.voice = voice


def edge_rows(config: RemangaConfig) -> list[Row]:
    return [
        Row("Narrator voice", config.tts.edge.voice_label, _pick_edge_voice, "the voice that reads every panel",
            keys=("tts.edge.voice",)),
    ]
