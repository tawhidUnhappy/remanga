"""Retakes: a take that hums between two words (audio/hums.py) made again
under other seeds, a retake kept only where it hums less and still reads its
script. Also the one place takes are sent to whisper for word timings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from remanga import activity
from remanga.audio.batching import Batch
from remanga.audio.clips import atomic_export
from remanga.audio.hums import Hum, find_hums
from remanga.audio.resample import load_audio
from remanga.audio.takes import collapsed
from remanga.config import AudioConfig, SubtitlesConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json_or, write_json
from remanga.plugins.faster_whisper.transcribe import Transcriber
from remanga.subtitles.align import align

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
        synth.seed = attempt
        synth.use_whole_text()
        synth.ensure_ready()
        retakes: dict[str, Path] = {}
        try:
            with activity.progress(f"Retaking hums (try {attempt} of {MAX_RETAKES})",
                                   total=len(humming), unit="takes") as bar:
                for name, (batch, _) in humming.items():
                    raw = audio_dir / f"{name}_raw.wav"
                    clip = audio_dir / f"{name}_retake.wav"
                    synth.synthesize(text=batch.text, output_wav=raw)
                    atomic_export(load_audio(raw, audio_config.sample_rate, channels=1), clip)
                    raw.unlink(missing_ok=True)
                    tried[name] = attempt
                    if collapsed(clip, batch):
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
        for (clip, out_json), name in zip(pairs, retakes, strict=True):
            batch, old = humming[name]
            document = json.loads(out_json.read_text(encoding="utf-8"))
            new = find_hums(clip, document["words"])
            better = (_hum_seconds(new) < _hum_seconds(old)
                      and _match_ratio(batch, document) >= _match_ratio(batch, timings[name]) - 0.01)
            if not better:
                clip.unlink(missing_ok=True)
                out_json.unlink(missing_ok=True)
                continue
            clip.replace(audio_dir / f"{name}.wav")
            # The json names the audio it was read from; it now IS that audio.
            document["audio_file"] = f"{name}.wav"
            write_json(subs_dir / f"{name}.json", document)
            out_json.unlink(missing_ok=True)
            timings[name] = document
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
