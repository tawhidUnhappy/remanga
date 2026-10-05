"""IndexTTS-2.5's rows on the Settings screen: which recording narrates, and
how fast. See ui/voice_settings.py for the rows every engine shares and how a
row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.index_tts.config import VOICE_DIR, recordings
from remanga.ui.dialogs import Ask, Choice, number_check
from remanga.ui.voice_rows import Row, wait_for


async def _pick_index_voice(screen, config: RemangaConfig) -> None:
    found = recordings()
    if not found:
        screen.notify(f"No recordings yet - put a clean recording of one person in {VOICE_DIR}/.", timeout=8)
        return
    current = config.tts.index_tts.reference_path()
    picked = await wait_for(screen)(Choice(
        "Narrator voice", [(path.name, "read every panel in this recording's voice", path.name)
                           for path in found],
        current=current.name if current else None,
        note=f"The recordings in {VOICE_DIR}/. IndexTTS takes the voice from the first 15 seconds and "
             f"needs no transcript. Changing this narrates chapters again."))
    if picked:
        config.tts.index_tts.reference = picked


async def _set_index_speed(screen, config: RemangaConfig) -> None:
    speed = await wait_for(screen)(Ask(
        "Speaking speed", "Speed (1.0 is normal)", value=f"{config.tts.index_tts.speed:g}",
        check=number_check(0.5, 2.0),
        note="1.0 is the recording's own pace. The model stretches or shortens the reading itself, "
             "so the pitch stays put. Changing this narrates every chapter again."))
    if speed is not None:
        config.tts.index_tts.speed = float(speed)


def index_tts_rows(config: RemangaConfig) -> list[Row]:
    index = config.tts.index_tts
    return [
        Row("Narrator voice", index.voice_label, _pick_index_voice, "the recording that reads every panel",
            keys=("tts.index_tts.reference",)),
        Row("Speaking speed", f"{index.speed:g}x", _set_index_speed, "how fast it talks (1 = normal)",
            keys=("tts.index_tts.speed",)),
    ]
