"""Tightening the pauses inside a synthesized take: every silence longer than
`audio.max_gap_ms` is cut down to it.

Kokoro breathes like a person reading aloud - measured on an 18-minute
whole-chapter take: 418 pauses over 100 ms, median 0.39 s, 155 of them over
half a second, 18% of the take silent. Natural, but not how a manga recap
channel sounds: those run the voice on with barely a breath between
sentences (user request, 2026-10-18).

Done to the take as it comes back from the engine, before anything reads it
- the hum check, faster-whisper's word timings, the panel spans - so the
video is cut to the tightened audio and nothing downstream knows it was
ever longer. Changing the cap therefore remakes the takes: it is part of
the narration's identity (narration_identity), but only when it is on, so
chapters narrated with natural pauses keep their keys."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from pydub import AudioSegment

from remanga.audio.resample import load_audio
from remanga.config import AudioConfig, TTSConfig

# 10 ms frames; a frame this far under the take's loud frames is silence.
FRAME_MS = 10
SILENCE_UNDER_DB = 35.0
# Each cut is a crossfade this long, so the join can never click.
CROSSFADE_MS = 8


def _frames(seg: AudioSegment) -> np.ndarray:
    full = 1 << (8 * seg.sample_width - 1)
    return np.array(seg.get_array_of_samples(), dtype=np.float64).reshape(-1, seg.channels) / full


def silent_runs(seg: AudioSegment) -> list[tuple[int, int]]:
    """(start, end) sample offsets of every silent stretch, edges included."""
    x = _frames(seg)
    step = max(1, seg.frame_rate * FRAME_MS // 1000)
    usable = len(x) // step * step
    if not usable:
        return []
    rms = np.sqrt(np.mean(x[:usable].reshape(-1, step, x.shape[1]) ** 2, axis=(1, 2)))
    loud = np.percentile(rms, 95)
    if loud <= 0:
        return []
    quiet = rms < loud * 10 ** (-SILENCE_UNDER_DB / 20)
    runs, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            runs.append((start * step, i * step))
            start = None
    if start is not None:
        runs.append((start * step, len(x)))
    return runs


def tighten_gaps(seg: AudioSegment, max_gap_ms: int) -> AudioSegment:
    """`seg` with every inner silence longer than `max_gap_ms` cut down to
    it - the middle taken out, the silence either side kept, so a word's
    tail and the next word's breath-in are never clipped. The silence at the
    very start and end is left alone: the panel spans trim those."""
    if max_gap_ms <= 0:
        return seg
    x = _frames(seg)
    keep = seg.frame_rate * max_gap_ms // 1000
    fade = min(seg.frame_rate * CROSSFADE_MS // 1000, keep // 2)
    pieces, at = [], 0
    for start, end in silent_runs(seg):
        if start == 0 or end >= len(x) or end - start <= keep:
            continue
        cut_from, cut_to = start + keep // 2, end - (keep - keep // 2)
        pieces.append(x[at:cut_from])
        at = cut_to
    if not pieces:
        return seg
    pieces.append(x[at:])
    out = pieces[0]
    for piece in pieces[1:]:
        if fade > 0 and len(out) >= fade and len(piece) >= fade:
            ramp = np.linspace(0.0, 1.0, fade)[:, None]
            joined = out[-fade:] * (1 - ramp) + piece[:fade] * ramp
            out = np.concatenate([out[:-fade], joined, piece[fade:]])
        else:
            out = np.concatenate([out, piece])
    full = 1 << (8 * seg.sample_width - 1)
    ints = np.clip(np.round(out * full), -full, full - 1).astype({2: np.int16, 4: np.int32}[seg.sample_width])
    return seg._spawn(ints.reshape(-1).tobytes())


def load_take(raw: Path, audio_config: AudioConfig) -> AudioSegment:
    """A take as the engine wrote it, at the project's rate, pauses tightened."""
    return tighten_gaps(load_audio(raw, audio_config.sample_rate, channels=1), audio_config.max_gap_ms)


def narration_identity(tts_config: TTSConfig, audio_config: AudioConfig) -> dict[str, Any]:
    """What the takes on disk were made with: the voice, and the pause cap
    when there is one - a take with its pauses cut is a different take."""
    identity = tts_config.identity()
    if audio_config.max_gap_ms > 0:
        identity = {**identity, "max_gap_ms": int(audio_config.max_gap_ms)}
    return identity
