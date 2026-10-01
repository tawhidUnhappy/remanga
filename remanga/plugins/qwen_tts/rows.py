"""Qwen3-TTS's settings rows: a preset narrator or a recording to clone, how
it reads (instruct), and designing a new voice from a description. See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.paths import GLOBAL_DIR
from remanga.plugins.qwen_tts.config import QWEN_SPEAKERS, RECORDING_PREFIX
from remanga.ui.dialogs import Ask, Choice
from remanga.ui.voice_rows import Row, wait_for

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
    picked = await wait_for(screen)(Choice(
        "Narrator voice", options, current="__designed__" if qwen.designed else qwen.speaker,
        note="Qwen3-TTS's preset narrators, or the voice you designed. Changing this narrates "
             "chapters again."))
    if picked == "__designed__":
        qwen.designed_sample = qwen.designed_sample or ""
    elif picked and picked.startswith("clone:"):
        # A recording of someone real: no transcript, so the clone works from
        # the speaker embedding (see plugins/qwen_tts/synth.py).
        path = picked[len("clone:"):]
        qwen.design, qwen.designed_sample, qwen.designed_text = RECORDING_PREFIX + Path(path).name, path, ""
    elif picked:
        qwen.speaker, qwen.design = picked, ""


async def _set_qwen_instruct(screen, config: RemangaConfig) -> None:
    instruct = await wait_for(screen)(Ask(
        "Delivery", "How the narrator reads (leave empty for the voice's own way)",
        value=config.tts.qwen.instruct,
        note="A note in plain words - \"calm and unhurried\", \"tense, quicker\". It steers a preset "
             "narrator; a designed voice already carries its own."))
    if instruct is not None:
        config.tts.qwen.instruct = instruct


async def _design_qwen_voice(screen, config: RemangaConfig) -> None:
    """Describe a narrator, hear one sample, keep it or try again."""
    from remanga.plugins.qwen_tts.synth import design_voice

    qwen = config.tts.qwen
    description = await wait_for(screen)(Ask(
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
    from remanga.plugins.qwen_tts.synth import DESIGN_SAMPLE_TEXT

    qwen.design, qwen.designed_sample = description, str(sample)
    qwen.designed_text = DESIGN_SAMPLE_TEXT   # what that sample says - see the clone mode
    screen.notify(f"The designed voice is in {sample} - listen to it, and design again if it is not right.",
                  timeout=8)


def qwen_rows(config: RemangaConfig) -> list[Row]:
    qwen = config.tts.qwen
    rows = [
        Row("Narrator voice", qwen.voice_label, _pick_qwen_voice,
            "the voice that reads every panel",
            keys=("tts.qwen.speaker", "tts.qwen.design", "tts.qwen.designed_sample", "tts.qwen.designed_text")),
        # An action, not a second copy of the voice: the voice in use is the
        # row above.
        Row("Design a new voice", "describe one in words", _design_qwen_voice,
            "make a new voice from a description"),
    ]
    if not qwen.designed:
        rows.insert(1, Row("Delivery", qwen.instruct or "the voice's own way", _set_qwen_instruct,
                           "tone of a preset voice, e.g. calm", keys=("tts.qwen.instruct",)))
    return rows
