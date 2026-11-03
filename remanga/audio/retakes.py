"""Retakes: a take made again under other seeds, a retake kept only where it
is better - one that hums between two words (audio/hums.py), and one that
left part of its script out. Also the one place takes are sent to whisper for
word timings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from remanga import activity
from remanga.audio.batching import Batch
from remanga.audio.clips import atomic_export
from remanga.audio.hums import Hum, find_hums
from remanga.audio.take_audio import load_take
from remanga.audio.takes import collapsed
from remanga.config import AudioConfig, SubtitlesConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json_or, write_json
from remanga.plugins.faster_whisper.transcribe import Transcriber
from remanga.subtitles.align import MIN_MATCH_RATIO, align

# How many times a take with a hum in it (audio/hums.py) is made again under
# another seed. Only the takes that hummed pay for it: a take's synthesis
# (about 1.4x its length on the 3060) and a transcription, each time.
MAX_RETAKES = 2


def hum_checked(timing_path: Path) -> set[str]:
    """The batches whose take was already checked for hums (and retaken if
    it had one) last time. Only meaningful for a take that is being reused:
    checking a take that stayed humming after its retakes again would only
    make the same retakes again."""
    previous = read_json_or(timing_path, {}) or {}
    return {row.get("name", "") for row in previous.get("batches", [])
            if isinstance(row, dict) and "retakes" in row}


def transcribe(subtitles_config: SubtitlesConfig, pairs: list[tuple[Path, Path]], label: str) -> None:
    """Word timings for each (take, json) pair, whisper loaded once for all."""
    transcriber = Transcriber(subtitles_config)
    try:
        transcriber.ensure_ready()
        with activity.progress(label, total=len(pairs), unit="batches") as bar:
            for wav, out_json in pairs:
                transcriber.words_for(wav, out_json)
                bar.advance()
    finally:
        transcriber.shutdown()


def _match_ratio(batch: Batch, document: dict[str, Any]) -> float:
    return align([(p.panel_id, p.text) for p in batch.panels], document["words"],
                 float(document["audio_duration_sec"])).match_ratio


def _hum_seconds(hums: list[Hum]) -> float:
    return sum(h.seconds for h in hums)


def retake_hums(synth, batches: list[Batch], timings: dict[str, dict[str, Any]], audio_dir: Path,
                 subs_dir: Path, subtitles_config: SubtitlesConfig, audio_config: AudioConfig,
                 checked: set[str]) -> dict[str, int]:
    """Takes with a hum in them (audio/hums.py) made again under other seeds,
    each kept only where the retake hums less and still reads its script.
    `timings` is updated in place for every take replaced. Returns how many
    retakes each batch had, which is recorded so a reused take is not
    retaken again on every run.

    A retake rather than cutting the hum out: whisper can miss a real word
    (an unusual name, most often), and cutting would take that word with it.
    A retake only ever swaps one whole reading of the script for another."""
    tried = {b.name: 0 for b in batches}
    humming: dict[str, tuple[Batch, list[Hum]]] = {}
    for batch in batches:
        if batch.name in checked:
            continue
        hums = find_hums(audio_dir / f"{batch.name}.wav", timings[batch.name]["words"])
        if hums:
            humming[batch.name] = (batch, hums)
            console.print(f"[yellow]{_esc(batch.name)}: voice with no words in it at "
                          f"{_esc('; '.join(h.describe() for h in hums))}[/]")
    if not humming:
        return tried
    if not hasattr(synth, "seed"):
        console.print(f"[dim]{_esc(synth.display_name)} reads a text the same way every time, "
                      f"so a retake would come back the same.[/]")
        return tried

    for attempt in range(1, MAX_RETAKES + 1):
        read = _read_again(synth, {name: batch for name, (batch, _) in humming.items()}, attempt,
                           f"Retaking hums (try {attempt} of {MAX_RETAKES})", audio_dir, subs_dir,
                           subtitles_config, audio_config)
        for name in humming:
            tried[name] = attempt
        for name, (clip, out_json, document) in read.items():
            batch, old = humming[name]
            new = find_hums(clip, document["words"])
            better = (_hum_seconds(new) < _hum_seconds(old)
                      and _match_ratio(batch, document) >= _match_ratio(batch, timings[name]) - 0.01)
            if not better:
                clip.unlink(missing_ok=True)
                out_json.unlink(missing_ok=True)
                continue
            _keep(name, clip, out_json, document, audio_dir, subs_dir, timings)
            if new:
                humming[name] = (batch, new)
            else:
                del humming[name]
                console.print(f"[green]{_esc(name)}: retake {attempt} came back clean[/]")
        if not humming:
            break

    for name, (_, hums) in humming.items():
        console.print(f"[yellow]{_esc(name)}: still has voice with no words in it after "
                      f"{MAX_RETAKES} retakes ({_esc('; '.join(h.describe() for h in hums))}) - "
                      f"kept the take with the least of it[/]")
    return tried


def _read_again(synth, batches: dict[str, Batch], attempt: int, label: str, audio_dir: Path, subs_dir: Path,
                subtitles_config: SubtitlesConfig, audio_config: AudioConfig) -> dict[str, tuple[Path, Path, dict]]:
    """Each batch read again under seed `attempt` and transcribed: name ->
    (the retake, its word timings' file, those timings). A retake that
    collapsed (audio/takes.py) is dropped here."""
    synth.seed = attempt
    synth.use_whole_text()
    synth.ensure_ready()
    retakes: dict[str, Path] = {}
    try:
        with activity.progress(label, total=len(batches), unit="takes") as bar:
            for name, batch in batches.items():
                raw = audio_dir / f"{name}_raw.wav"
                clip = audio_dir / f"{name}_retake.wav"
                synth.synthesize(text=batch.text, output_wav=raw)
                atomic_export(load_take(raw, audio_config), clip)
                raw.unlink(missing_ok=True)
                if collapsed(clip, batch, synth.ceiling_seconds):
                    clip.unlink(missing_ok=True)
                else:
                    retakes[name] = clip
                bar.advance()
    finally:
        synth.seed = 0
        # Whisper needs the GPU next.
        synth.shutdown()

    pairs = [(clip, subs_dir / f"{name}_retake.json") for name, clip in retakes.items()]
    if pairs:
        transcribe(subtitles_config, pairs, "Reading the retakes")
    return {name: (clip, out_json, json.loads(out_json.read_text(encoding="utf-8")))
            for (clip, out_json), name in zip(pairs, retakes, strict=True)}


def _keep(name: str, clip: Path, out_json: Path, document: dict, audio_dir: Path, subs_dir: Path,
          timings: dict[str, dict[str, Any]]) -> None:
    """A retake put in place of its take, with its word timings."""
    clip.replace(audio_dir / f"{name}.wav")
    # The json names the audio it was read from; it now IS that audio.
    document["audio_file"] = f"{name}.wav"
    write_json(subs_dir / f"{name}.json", document)
    out_json.unlink(missing_ok=True)
    timings[name] = document


# How many times a take that left part of its script out is read again. The
# seeds start past the hum retakes' so the two never read a take the same way.
MAX_MISMATCH_RETAKES = 3
MISMATCH_SEED_FROM = 10


def retake_mismatches(synth, batches: list[Batch], timings: dict[str, dict[str, Any]], audio_dir: Path,
                      subs_dir: Path, subtitles_config: SubtitlesConfig, audio_config: AudioConfig) -> None:
    """Takes under MIN_MATCH_RATIO of their script (subtitles/align.py) read
    again under other seeds, keeping the best reading. `timings` is updated in
    place. A take still under it afterwards is left for align.check to refuse.

    Fish Audio Drama 3 leaves out a sentence now and then even a page at a
    time (2 of 32 takes of a chapter: 85% and 49%); read again, the sentence
    is there. An engine that reads a text the same way every time has no
    `seed`, and nothing is retaken."""
    failing = {b.name: b for b in batches if _match_ratio(b, timings[b.name]) < MIN_MATCH_RATIO}
    if not failing or not hasattr(synth, "seed"):
        return
    for name, batch in failing.items():
        console.print(f"[yellow]{_esc(name)}: only {_match_ratio(batch, timings[name]):.0%} of its script "
                      f"is in the take - reading it again[/]")
    for attempt in range(1, MAX_MISMATCH_RETAKES + 1):
        read = _read_again(synth, failing, MISMATCH_SEED_FROM + attempt,
                           f"Retaking takes that left words out (try {attempt} of {MAX_MISMATCH_RETAKES})",
                           audio_dir, subs_dir, subtitles_config, audio_config)
        for name, (clip, out_json, document) in read.items():
            batch = failing[name]
            new, old = _match_ratio(batch, document), _match_ratio(batch, timings[name])
            if new <= old:
                clip.unlink(missing_ok=True)
                out_json.unlink(missing_ok=True)
                continue
            _keep(name, clip, out_json, document, audio_dir, subs_dir, timings)
            if new >= MIN_MATCH_RATIO:
                del failing[name]
                console.print(f"[green]{_esc(name)}: retake {attempt} reads {new:.0%} of its script[/]")
        if not failing:
            return
