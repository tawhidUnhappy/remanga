"""The narrator's rows on the settings screen, per engine.

Each engine takes a voice in its own way - a name from a catalogue, a preset
plus a note on delivery, a description to design from - so each one says here
what its rows are and what changing one asks. The settings screen itself only
knows about `Row`, so adding an engine is a function here and its name in
ENGINE_ROWS, with nothing in the screen to update.

The rows are built fresh each time the screen loads, so a row can appear only
when it applies (the sample line of a designed voice, say)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.config.kokoro_voices import KOKORO_VOICES
from remanga.config.tts import QWEN_SPEAKERS, RECORDING_PREFIX
from remanga.config.tts_engines import TTS_ENGINE_SPECS
from remanga.paths import GLOBAL_DIR
from remanga.ui.dialogs import Ask, Choice, number_check

# A screen that can `await self.app.push_screen_wait(dialog)` and reload.
Changer = Callable[["object", RemangaConfig], Awaitable[None]]


@dataclass
class Row:
    """One settings line: what it is called, what it says now, and what
    changing it does."""

    label: str
    value: str
    change: Changer
    # One short line on what the setting does, shown beside it, and the group
    # it belongs to (shown once, on the group's first row) - so the screen
    # reads without opening every row to find out.
    help: str = ""
    group: str = ""


def _wait(screen):
    return screen.app.push_screen_wait


# --- Kokoro -------------------------------------------------------------------


async def _pick_kokoro_voice(screen, config: RemangaConfig) -> None:
    voice = await _wait(screen)(Choice(
        "Narrator voice", [(v.label, f"grade {v.grade} · {v.accent}", v.name) for v in KOKORO_VOICES],
        current=config.tts.kokoro.voice,
        note="Kokoro-82M's own voices, best graded first. A new voice narrates chapters again."))
    if voice:
        config.tts.kokoro.voice = voice


async def _set_kokoro_speed(screen, config: RemangaConfig) -> None:
    speed = await _wait(screen)(Ask(
        "Speaking speed", "Speed (1.0 is normal)", value=f"{config.tts.kokoro.speed:g}",
        check=number_check(0.5, 2.0),
        note="1.0 is the voice's own pace, about 185 words a minute. Past about 1.35 Kokoro starts "
             "dropping the pauses between sentences. Changing this narrates every chapter again."))
    if speed is not None:
        config.tts.kokoro.speed = float(speed)


def kokoro_rows(config: RemangaConfig) -> list[Row]:
    kokoro = config.tts.kokoro
    return [
        Row("Narrator voice", kokoro.voice_label, _pick_kokoro_voice, "the voice that reads every panel"),
        Row("Speaking speed", f"{kokoro.speed:g}x", _set_kokoro_speed, "how fast it talks (1 = normal)"),
    ]


# --- Qwen3-TTS ----------------------------------------------------------------

VOICE_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus")


def _recordings() -> list[Path]:
    """The recordings in global/voice/ a voice can be cloned from. Skips what
    remanga wrote there itself: its own samples, and the trimmed copy it makes
    of a long reference."""
    folder = GLOBAL_DIR / "voice"
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir()
                  if path.is_file() and path.suffix.lower() in VOICE_EXTS
                  and not path.stem.startswith("sample_") and ".first" not in path.stem)


DESIGN_EXAMPLES = ("a calm middle-aged man telling a story by a fire, warm and unhurried",
                   "a young woman narrating an adventure, bright and quick")


async def _pick_qwen_voice(screen, config: RemangaConfig) -> None:
    qwen = config.tts.qwen
    options = [(name.replace("_", " "), hint, name) for name, hint in QWEN_SPEAKERS]
    recordings = _recordings()
    options += [(f"Clone {path.name}", "read every panel in that recording's voice", f"clone:{path}")
                for path in recordings]
    if qwen.design:
        options.insert(0, (f"Designed: {qwen.design[:40]}", "the voice you described", "__designed__"))
    picked = await _wait(screen)(Choice(
        "Narrator voice", options, current="__designed__" if qwen.designed else qwen.speaker,
        note="Qwen3-TTS's preset narrators, or the voice you designed. Changing this narrates "
             "chapters again."))
    if picked == "__designed__":
        qwen.designed_sample = qwen.designed_sample or ""
    elif picked and picked.startswith("clone:"):
        # A recording of someone real: no transcript, so the clone works from
        # the speaker embedding (see audio/synth/qwen.py).
        path = picked[len("clone:"):]
        qwen.design, qwen.designed_sample, qwen.designed_text = RECORDING_PREFIX + Path(path).name, path, ""
    elif picked:
        qwen.speaker, qwen.design = picked, ""


async def _set_qwen_instruct(screen, config: RemangaConfig) -> None:
    instruct = await _wait(screen)(Ask(
        "Delivery", "How the narrator reads (leave empty for the voice's own way)",
        value=config.tts.qwen.instruct,
        note="A note in plain words - \"calm and unhurried\", \"tense, quicker\". It steers a preset "
             "narrator; a designed voice already carries its own."))
    if instruct is not None:
        config.tts.qwen.instruct = instruct


async def _design_qwen_voice(screen, config: RemangaConfig) -> None:
    """Describe a narrator, hear one sample, keep it or try again."""
    from remanga.audio.synth.qwen import design_voice

    qwen = config.tts.qwen
    description = await _wait(screen)(Ask(
        "Design a new voice", "Describe the narrator", value=qwen.design or DESIGN_EXAMPLES[0],
        note=f"For example: {DESIGN_EXAMPLES[1]}. One sample is made and kept - every panel is then "
             f"spoken from that sample, so the voice stays the same across a chapter."))
    if not description:
        return
    folder = GLOBAL_DIR / "voice"
    sample = folder / "designed.wav"
    outcome = await screen.run_work("Designing the voice", "Qwen3-TTS (this downloads the model once)",
                                    lambda: design_voice(qwen, description, sample))
    if not outcome:
        return
    from remanga.audio.synth.qwen import DESIGN_SAMPLE_TEXT

    qwen.design, qwen.designed_sample = description, str(sample)
    qwen.designed_text = DESIGN_SAMPLE_TEXT   # what that sample says - see the clone mode
    screen.notify(f"The designed voice is in {sample} - listen to it, and design again if it is not right.",
                  timeout=8)


def qwen_rows(config: RemangaConfig) -> list[Row]:
    qwen = config.tts.qwen
    rows = [
        Row("Narrator voice", qwen.voice_label, _pick_qwen_voice,
            "the voice that reads every panel"),
        # An action, not a second copy of the voice: the voice in use is the
        # row above.
        Row("Design a new voice", "describe one in words", _design_qwen_voice,
            "make a new voice from a description"),
    ]
    if not qwen.designed:
        rows.insert(1, Row("Delivery", qwen.instruct or "the voice's own way", _set_qwen_instruct,
                           "tone of a preset voice, e.g. calm"))
    return rows


# --- the engine itself --------------------------------------------------------

ENGINE_ROWS: dict[str, Callable[[RemangaConfig], list[Row]]] = {
    "kokoro": kokoro_rows,
    "qwen": qwen_rows,
}


async def _pick_engine(screen, config: RemangaConfig) -> None:
    engine = await _wait(screen)(Choice(
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
                "the text-to-speech system")]
    rows += ENGINE_ROWS.get(config.tts.spec.name, kokoro_rows)(config)
    if config.tts.engine_block.voice_options():
        rows.append(Row("Hear the voices", "make samples", _hear_voices,
                        "one sample line per voice, to compare"))
    for row in rows:
        row.group = "Narration"
    return rows
