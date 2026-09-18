"""Hearing the narrator before committing a chapter to it.

One line, read in every voice the configured engine has, written to
global/voice/samples/<engine>/. One worker for the whole set, so the model
loads once - which for a big engine is most of the time."""

from __future__ import annotations

from pathlib import Path

from remanga import activity
from remanga.audio.clips import atomic_export
from remanga.audio.resample import load_audio
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.paths import GLOBAL_DIR

# Long enough to hear a voice's pace and register, short enough to sit
# through nine of them. Deliberately narration, not a greeting: it is the job
# the voice is being auditioned for.
SAMPLE_TEXT = (
    "Evening falls over the royal capital, and the boy in the tattered cloak drinks from the well, "
    "thinking that after three days without water he truly believed he would die. However, a girl "
    "carrying a basket stops behind him and tells him that the well belongs to the baker."
)


def samples_dir(engine: str) -> Path:
    return GLOBAL_DIR / "voice" / "samples" / engine


def sample_voices(config: RemangaConfig, text: str = SAMPLE_TEXT) -> list[Path]:
    """The same line in every voice of the configured engine. Returns the
    files written, in the order the voice list has them."""
    from remanga.audio.synth import create_synthesizer

    engine = config.tts.spec
    voices = config.tts.engine_block.voice_options()
    if not voices:
        raise ValueError(f"{engine.display_name} has no voices to sample - it takes a recording or a "
                         f"description instead.")

    out_dir = samples_dir(engine.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    synth = create_synthesizer(config.tts, config.audio)
    console.print(f"[cyan]Reading one line in each of {engine.display_name}'s {len(voices)} voice(s)[/]")
    synth.ensure_ready()

    written: list[Path] = []
    with activity.progress("Sampling voices", total=len(voices), unit="voices") as bar:
        for name, _hint in voices:
            raw = out_dir / f"{name}.raw.wav"
            final = out_dir / f"{name}.wav"
            synth.synthesize(text=text, output_wav=raw, voice=name)
            atomic_export(load_audio(raw, config.audio.sample_rate, channels=1), final)
            raw.unlink(missing_ok=True)
            written.append(final)
            bar.advance()

    delivery = getattr(config.tts.engine_block, "instruct", "")
    (out_dir / "what-they-say.txt").write_text(
        f"{engine.display_name} voices, each reading:\n\n{text}\n\n"
        + (f"Delivery asked for: {delivery}\n\n" if delivery else "")
        + "\n".join(f"{name}.wav - {hint}" for name, hint in voices) + "\n", encoding="utf-8")
    console.print(f"[bold green]✓ {len(written)} sample(s) in[/] {_esc(str(out_dir))}")
    return written
