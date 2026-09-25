"""Narrating a chapter in a few long takes instead of one per panel.

A panel synthesized on its own is a generation on its own: Qwen chooses the
pitch, pace and weight of the line from that line alone, so two panels of one
scene come back in audibly different voices. Trimming the silence between
them made the joins tight and changed nothing about it, because it was never
silence - it was a new take. The only thing that keeps a chapter in one voice
is asking for it in one go.

So the panels are joined into batches (audio/batching.py), each batch is one
call, and where each panel lands inside the result is read back off the audio
afterwards (remanga/subtitles/). Every panel still gets its own row in
audio_timing.json - pointing into its batch rather than at a clip of its own -
so the mix, the frame timeline and the render never learn that any of this
changed.

The rows are contiguous: one panel ends exactly where the next begins, at the
midpoint of the silence between their words. Laid end to end they reproduce
the take sample for sample, which is the point - there is no gap to insert
and nothing of the take to drop."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga import activity
from remanga.audio.batching import TOKEN_CEILING_SECONDS, Batch, plan_batches
from remanga.audio.clips import atomic_export, speech_bounds
from remanga.audio.manifest import verify_audio_manifest, write_audio_manifest
from remanga.audio.resample import load_audio
from remanga.audio.timing import panel_timing, write_timing
from remanga.config import AudioConfig, SubtitlesConfig, TTSConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json_or
from remanga.narration import StoryPanel
from remanga.paths import get_audio_dir, get_audio_timing_path, get_subtitles_dir
from remanga.subtitles.align import align, check
from remanga.subtitles.manifest import verify_subtitle_manifest, write_subtitle_manifest
from remanga.subtitles.transcribe import Transcriber, audio_seconds

# How much longer than its own estimate a take may come back before it is
# read as a collapse rather than a slow reading. Measured on a good take, the
# estimate is within 1%: 4,611 characters asked for ~205s and came back 203s.
RUNAWAY_FACTOR = 1.4

# How many times a take may be halved before giving up. Three takes a batch
# down to an eighth, which is far below anything that has ever collapsed.
MAX_SPLIT_DEPTH = 3


def _collapsed(clip: Path, batch: Batch) -> str | None:
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


def _source_key(text: str, voice: dict[str, Any]) -> str:
    """What this batch was asked for: its text and the voice reading it. A
    batch whose key still matches is the take that text asks for, so it is
    reused; a batch whose key changed has to be made again, and only that
    one - which is why batches break on pages (audio/batching.py)."""
    payload = json.dumps({"text": text, "voice": voice}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _recorded_keys(timing_path: Path) -> dict[str, str]:
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
    if not force and clip.exists() and recorded.get(batch.name) == _source_key(batch.text, voice):
        reused.add(batch.name)
        return [batch]

    console.print(f"[dim]{_esc(batch.name)}: {len(batch.panels)} panels, {len(batch.text)} chars, "
                  f"about {batch.estimated_seconds / 60:.1f} min[/]")
    raw = audio_dir / f"{batch.name}_raw.wav"
    synth.synthesize(text=batch.text, output_wav=raw)
    atomic_export(load_audio(raw, audio_config.sample_rate, channels=1), clip)
    raw.unlink(missing_ok=True)

    problem = _collapsed(clip, batch)
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


def _synthesize_batches(synth, planned: list[Batch], audio_dir: Path, audio_config: AudioConfig,
                        voice: dict[str, Any], recorded: dict[str, str], force: bool,
                        reused: set[str]) -> list[Batch]:
    """Every planned take made, in order. The list that comes back is what is
    actually on disk, which is not the plan when a take had to be split."""
    if any(force or not (audio_dir / f"{b.name}.wav").exists()
           or recorded.get(b.name) != _source_key(b.text, voice) for b in planned):
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


def _read_timings(subtitles_config: SubtitlesConfig, batches: list[Batch], audio_dir: Path,
                  subs_dir: Path, reuse: set[str]) -> dict[str, dict[str, Any]]:
    """Each batch's word timings, transcribed unless the batch's audio is
    unchanged and its timings are already beside it."""
    needed = [b for b in batches
              if b.name not in reuse or not (subs_dir / f"{b.name}.json").exists()]
    if not needed:
        return {b.name: json.loads((subs_dir / f"{b.name}.json").read_text(encoding="utf-8"))
                for b in batches}

    transcriber = Transcriber(subtitles_config)
    try:
        transcriber.ensure_ready()
        with activity.progress("Reading word timings", total=len(needed), unit="batches") as bar:
            for batch in needed:
                transcriber.words_for(audio_dir / f"{batch.name}.wav", subs_dir / f"{batch.name}.json")
                bar.advance()
    finally:
        transcriber.shutdown()

    return {b.name: json.loads((subs_dir / f"{b.name}.json").read_text(encoding="utf-8"))
            for b in batches}


def _batch_rows(batch: Batch, spans, timeline_ms: int, pause_after_batch_ms: int,
                index_from: int) -> tuple[list[dict[str, Any]], int]:
    """One batch's panels as audio_timing rows, laid end to end."""
    rows: list[dict[str, Any]] = []
    last = len(spans) - 1
    for offset, span in enumerate(spans):
        pause = pause_after_batch_ms if offset == last else 0
        rows.append(panel_timing(
            index_from + offset, span.panel_id, batch.panels[offset].text, f"{batch.name}.wav",
            start_ms=timeline_ms, duration_ms=span.end_ms - span.start_ms,
            pause_after_ms=pause, clip_start_ms=span.start_ms,
            # Only the batch's own ends are real edges; the joins inside it
            # are adjacent samples of one take.
            fade_in=offset == 0, fade_out=offset == last,
        ))
        timeline_ms += (span.end_ms - span.start_ms) + pause
    return rows, timeline_ms


def _trim_edges(spans, clip: Path):
    """The batch's own lead-in and tail silence taken off its first and last
    panel. Inside the batch there is nothing to trim - the model chose those
    pauses and they are part of the reading."""
    bounds_start, bounds_end = speech_bounds(AudioSegment.from_file(clip))
    trimmed = list(spans)
    first, last = trimmed[0], trimmed[-1]
    trimmed[0] = type(first)(first.panel_id, max(first.start_ms, bounds_start),
                             first.end_ms, first.matched_words)
    trimmed[-1] = type(last)(last.panel_id, trimmed[-1].start_ms,
                             min(last.end_ms, bounds_end), last.matched_words)
    return trimmed


def narrate_in_batches(synth, tts_config: TTSConfig, audio_config: AudioConfig,
                       subtitles_config: SubtitlesConfig, project_name: str, chapter_num: str,
                       panels: list[StoryPanel], force: bool = False) -> Path:
    """A chapter narrated in batches, from planning to audio_timing.json."""
    audio_dir = get_audio_dir(project_name, chapter_num)
    subs_dir = get_subtitles_dir(project_name, chapter_num)
    for stray in audio_dir.glob("*.wav.tmp"):
        stray.unlink(missing_ok=True)

    if not force:
        verify_audio_manifest(audio_dir, chapter_num)
        verify_subtitle_manifest(subs_dir, chapter_num)

    planned = plan_batches(panels, audio_config.batch_target_minutes)
    voice_identity = tts_config.identity()
    timing_path = get_audio_timing_path(project_name, chapter_num)
    recorded = _recorded_keys(timing_path)

    console.print(f"[cyan]Narrating {len(panels)} panel(s) as {len(planned)} take(s) with "
                  f"{synth.display_name}[/] [dim]({_esc(tts_config.voice_detail)})[/]")

    # What comes back is what is on disk, which is not the plan when a take
    # collapsed and had to be split.
    reused: set[str] = set()
    batches = _synthesize_batches(synth, planned, audio_dir, audio_config, voice_identity,
                                  recorded, force, reused)
    # The TTS model is done; let go of the GPU before whisper asks for it.
    synth.shutdown()

    keys = {b.name: _source_key(b.text, voice_identity) for b in batches}
    timings = _read_timings(subtitles_config, batches, audio_dir, subs_dir, reused)

    rows: list[dict[str, Any]] = []
    timeline_ms = 0
    for batch in batches:
        document = timings[batch.name]
        alignment = align([(p.panel_id, p.text) for p in batch.panels],
                          document["words"], float(document["audio_duration_sec"]))
        check(alignment, batch.name)
        spans = _trim_edges(alignment.spans, audio_dir / f"{batch.name}.wav")
        console.print(f"[dim]{_esc(batch.name)}: {alignment.match_ratio:.0%} of the narration "
                      f"matched what was said[/]")
        batch_rows, timeline_ms = _batch_rows(
            batch, spans, timeline_ms, audio_config.pause_between_panels_ms, len(rows) + 1)
        rows.extend(batch_rows)

    write_timing(timing_path, chapter_num, rows, total_ms=timeline_ms, voice=voice_identity,
                 batches=[{"name": b.name, "source_sha256": keys[b.name],
                           "panels": [p.panel_id for p in b.panels]} for b in batches])

    wanted_audio = {f"{b.name}.wav" for b in batches}
    wanted_subs = {f"{b.name}.json" for b in batches}
    for stale in audio_dir.glob("*.wav"):
        if stale.name not in wanted_audio:
            stale.unlink(missing_ok=True)
    for stale in subs_dir.glob("*.json"):
        if stale.name not in wanted_subs and stale.name != "subtitle_manifest.json":
            stale.unlink(missing_ok=True)

    write_audio_manifest(audio_dir, chapter_num, sorted(wanted_audio))
    write_subtitle_manifest(subs_dir, chapter_num, sorted(wanted_subs))

    if reused:
        console.print(f"[dim cyan](Reused {len(reused)} take(s) already narrated in this voice)[/]")
    console.print(f"[bold green]✓ Narration synthesized for {len(panels)} panel(s) "
                  f"in {len(batches)} take(s)[/]")
    return timing_path
