"""The narrator's rows on the settings screen, per engine.

Each engine takes a voice in its own way - a name from a catalogue, a preset
plus a note on delivery, a description to design from - so each one says here
what its rows are and what changing one asks. The settings screen itself only
knows about `Row`, so adding an engine is a function here and its name in
ENGINE_ROWS, with nothing in the screen to update.

The rows are built fresh each time the screen loads, so a row can appear only
when it applies (the sample line of a designed voice, say)."""

from __future__ import annotations

from collections.abc import Callable

from remanga.config import RemangaConfig
from remanga.config.kokoro_voices import KOKORO_VOICES
from remanga.config.tts_engines import TTS_ENGINE_SPECS
from remanga.ui.dialogs import Ask, Choice, number_check
from remanga.ui.voice_rows import Row, wait_for
from remanga.ui.voice_settings_qwen import qwen_rows

# A screen that can `await self.app.push_screen_wait(dialog)` and reload.


# --- Kokoro -------------------------------------------------------------------


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


# --- Qwen3-TTS ----------------------------------------------------------------


# --- the engine itself --------------------------------------------------------

ENGINE_ROWS: dict[str, Callable[[RemangaConfig], list[Row]]] = {
    "kokoro": kokoro_rows,
    "qwen": qwen_rows,
}


async def _pick_engine(screen, config: RemangaConfig) -> None:
    engine = await wait_for(screen)(Choice(
        "Narrator engine", [(spec.display_name, spec.summary, spec.name) for spec in TTS_ENGINE_SPECS],
        current=config.tts.engine,
        note="Each engine keeps its own voice, so switching back and forth changes nothing else. "
             "A chapter narrated by the other engine is narrated again."))
    if engine:
        config.tts.engine = engine


async def _hear_voices(screen, config: RemangaConfig) -> None:
    """One line read in every voice this engine has, to listen to and choose
    from - the model loads once for the whole set."""
    from remanga import workflow

    ok = await screen.run_work("Sampling the voices", f"{config.tts.spec.display_name}: one line per voice",
                               lambda: workflow.sample_voices(config))
    if ok:
        screen.notify(f"The samples are in {workflow.samples_dir(config.tts.spec.name)}/ - listen, then pick "
                      f"the voice here.", timeout=10)


def narrator_rows(config: RemangaConfig) -> list[Row]:
    """The engine, then whatever that engine's voice needs."""
    rows = [Row("Narrator engine", config.tts.spec.display_name, _pick_engine,
                "the text-to-speech system", keys=("tts.engine",))]
    rows += ENGINE_ROWS.get(config.tts.spec.name, kokoro_rows)(config)
    if config.tts.engine_block.voice_options():
        rows.append(Row("Hear the voices", "make samples", _hear_voices,
                        "one sample line per voice, to compare"))
    for row in rows:
        row.group = "Narration"
    return rows
