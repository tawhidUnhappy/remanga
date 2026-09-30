"""Making a chapter's takes: one generation per batch of panels, reused while
its text and voice are unchanged, and halved and made again when it comes
back collapsed (silence to the end of the generation budget) - see
audio/batched.py for the whole narration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from remanga import activity
from remanga.audio.batching import TOKEN_CEILING_SECONDS, Batch
from remanga.audio.clips import atomic_export
from remanga.audio.resample import load_audio
from remanga.config import AudioConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json_or
from remanga.subtitles.transcribe import audio_seconds

# How much longer than its own estimate a take may come back before it is
# read as a collapse rather than a slow reading. Measured on a good take, the
# estimate is within 1%: 4,611 characters asked for ~205s and came back 203s.
RUNAWAY_FACTOR = 1.4


# How many times a take may be halved before giving up. Three takes a batch
# down to an eighth, which is far below anything that has ever collapsed.
MAX_SPLIT_DEPTH = 3


def collapsed(clip: Path, batch: Batch) -> str | None:
    """Why this take is not a reading of its script, or None if it looks
    like one.

    A take that collapses does not fail - Qwen keeps generating, producing
    nothing but silence, until its token budget runs out. Measured on a real
    chapter: 11,673 characters came back as 655.28s, the budget exactly, with
    three panels read and 2% of the script findable in it. Both symptoms are
    visible here, before a word of it is transcribed."""
    seconds = audio_seconds(clip)
    if seconds >= TOKEN_CEILING_SECONDS - 5:
        return (f"it ran to the model's {TOKEN_CEILING_SECONDS:.0f}s generation budget, which means "
                f"it stopped when it ran out rather than when it finished")
    if seconds > batch.estimated_seconds * RUNAWAY_FACTOR:
        return (f"it came back {seconds:.0f}s long where about {batch.estimated_seconds:.0f}s of "
                f"speech was asked for")
    return None


def source_key(text: str, voice: dict[str, Any]) -> str:
    """What this batch was asked for: its text and the voice reading it. A
    batch whose key still matches is the take that text asks for, so it is
    reused; a batch whose key changed has to be made again, and only that
    one - which is why batches break on pages (audio/batching.py)."""
    payload = json.dumps({"text": text, "voice": voice}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def recorded_keys(timing_path: Path) -> dict[str, str]:
    """The source key each batch on disk was made from, last time."""
    previous = read_json_or(timing_path, {}) or {}
    return {row.get("name", ""): row.get("source_sha256", "")
            for row in previous.get("batches", []) if isinstance(row, dict)}


def _make_take(synth, batch: Batch, audio_dir: Path, audio_config: AudioConfig,
               voice: dict[str, Any], recorded: dict[str, str], force: bool,
               reused: set[str], depth: int = 0) -> list[Batch]:
    """`batch` as audio on disk, halved and retried if the take collapses.

    Returns the batches actually made - the one asked for, or the pieces it
    had to become. A collapse is the model losing the thread on a long text,
    so the answer is a shorter text, and the split is where the plan would
    have broken anyway (a page boundary)."""
    clip = audio_dir / f"{batch.name}.wav"
    if not force and clip.exists() and recorded.get(batch.name) == source_key(batch.text, voice):
        reused.add(batch.name)
        return [batch]

    console.print(f"[dim]{_esc(batch.name)}: {len(batch.panels)} panels, {len(batch.text)} chars, "
                  f"about {batch.estimated_seconds / 60:.1f} min[/]")
    raw = audio_dir / f"{batch.name}_raw.wav"
    synth.synthesize(text=batch.text, output_wav=raw)
    atomic_export(load_audio(raw, audio_config.sample_rate, channels=1), clip)
    raw.unlink(missing_ok=True)

    problem = collapsed(clip, batch)
    if problem is None:
        return [batch]

    # Gone either way: a take that is not a reading of its script is not
    # something to leave lying in the audio folder, whether it is about to be
    # retried as two or about to fail the run. It would look finished to
    # anyone opening the folder, and to a resume that only checks a file is
    # there.
    clip.unlink(missing_ok=True)

    halves = batch.split()
    if halves is None or depth >= MAX_SPLIT_DEPTH:
        raise RuntimeError(
            f"Batch {batch.name} did not come back as its script: {problem}. It cannot be split any "
            f"further, so narrating it needs a shorter take - lower 'Narration take length' in settings."
        )
    console.print(f"[yellow]{_esc(batch.name)} did not come back as its script - {problem}. "
                  f"Narrating it as two shorter takes instead.[/]")
    return [made for half in halves
            for made in _make_take(synth, half, audio_dir, audio_config, voice, recorded,
                                   force, reused, depth + 1)]


def synthesize_batches(synth, planned: list[Batch], audio_dir: Path, audio_config: AudioConfig,
                        voice: dict[str, Any], recorded: dict[str, str], force: bool,
                        reused: set[str]) -> list[Batch]:
    """Every planned take made, in order. The list that comes back is what is
    actually on disk, which is not the plan when a take had to be split."""
    if any(force or not (audio_dir / f"{b.name}.wav").exists()
           or recorded.get(b.name) != source_key(b.text, voice) for b in planned):
        # One generation per take, whole: chunking it back into bounded calls
        # would put back exactly the seams this is here to remove.
        synth.use_whole_text()
        synth.ensure_ready()

    made: list[Batch] = []
    with activity.progress("Narrating takes", total=len(planned), unit="takes") as bar:
        for batch in planned:
            made.extend(_make_take(synth, batch, audio_dir, audio_config, voice,
                                   recorded, force, reused))
            bar.advance()
    return made
