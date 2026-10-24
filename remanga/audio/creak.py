"""Softening the creak a narrator ends its phrases with - the "rhh" on the
last syllable before a pause.

Kokoro's af_heart lets most phrase endings fall into vocal fry: the pitch
drops from ~200 Hz into irregular 50-90 Hz pulses, 10-20 dB under the voice,
nearly all of it under 1 kHz. Measured on 5 minutes of a whole-chapter take:
78% of the pauses follow 50 ms or more of it (a median 110 ms), against 12%
of frames inside sentences that look the same (user report, 2026-10-24:
"that annoying rhh sound after each sentence"). It is the end of the word,
not breath after it, so it is never cut: only its low rumble is turned down,
under LOW_HZ, where the pulses are and the syllable's sounds are not - and
the whole frame a little, so what is left sits back. A compressor lifts it
and a bass boost lifts exactly its band, which is why it runs first in the
voice chain (voice_chain.at_the_mic).

Analysis is at 16 kHz (enough for 50-400 Hz pitch); the gain is applied at
the track's own rate, ramped so it can never click. The track's length never
changes."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt

ANALYSIS_RATE = 16000
FRAME_MS = 10
# A frame this far under the track's loud frames is silence (as audio/gaps.py).
SILENCE_UNDER_DB = 35.0
MIN_PAUSE_MS = 80
# How far before a pause creak is looked for, and how loud a frame must be to
# count (quieter is already silence to the ear).
LOOK_BACK_MS = 400
AUDIBLE_UNDER_DB = 30.0
# YIN's cumulative-mean normalized difference never dips under this at any
# 50-400 Hz period in a creaky frame; modal voice dips to ~0.01-0.1.
# Calibrated on af_heart: 0.3 flags 78% of phrase ends and 12% of mid-sentence
# frames (0.2: 87% / 20%; 0.4: 65% / 6%).
APERIODIC = 0.3
LOW_SHARE = 0.6
LOW_HZ = 500
RAMP_MS = 20

# setting -> (dB on the band under LOW_HZ, dB on the whole frame)
CREAKS = {"soften": (-15.0, -4.0), "strong": (-28.0, -8.0)}


def _aperiodicity(w: np.ndarray, rate: int) -> float:
    """YIN's lowest normalized difference over 50-400 Hz periods (FFT form)."""
    w = w - w.mean()
    hi = rate // 50
    n = len(w) - hi
    if n <= 0:
        return 0.0
    size = 1 << (len(w) + n).bit_length()
    corr = np.fft.irfft(np.fft.rfft(w, size) * np.conj(np.fft.rfft(w[:n], size)), size)[1:hi + 1]
    sq = np.concatenate([[0.0], np.cumsum(w * w)])
    taus = np.arange(1, hi + 1)
    diff = sq[n] + (sq[taus + n] - sq[taus]) - 2 * corr
    cum = np.cumsum(diff)
    cmnd = diff * taus / np.where(cum > 0, cum, 1)
    return float(cmnd[rate // 400 - 1:].min())


def _low_share(w: np.ndarray, rate: int) -> float:
    spec = np.abs(np.fft.rfft(w * np.hanning(len(w)))) ** 2
    freqs = np.fft.rfftfreq(len(w), 1 / rate)
    total = spec[freqs < 8000].sum()
    return float(spec[freqs < 1000].sum() / total) if total > 0 else 0.0


def creak_frames(mono: np.ndarray, rate: int) -> np.ndarray:
    """A bool per FRAME_MS frame: creak running into a pause."""
    y = resample_poly(mono, ANALYSIS_RATE, rate) if rate != ANALYSIS_RATE else mono
    step = ANALYSIS_RATE * FRAME_MS // 1000
    count = len(y) // step
    flags = np.zeros(count, dtype=bool)
    if count < 3:
        return flags
    rms = np.sqrt((y[:count * step].reshape(count, step) ** 2).mean(axis=1)) + 1e-12
    db = 20 * np.log10(rms)
    loud = np.percentile(db, 95)
    quiet = db < loud - SILENCE_UNDER_DB
    half = 3 * step   # 60 ms: two periods at 50 Hz with room for the lag
    i = 1
    while i < count:
        if not (quiet[i] and not quiet[i - 1]):
            i += 1
            continue
        j = i
        while j < count and quiet[j]:
            j += 1
        if j - i >= MIN_PAUSE_MS // FRAME_MS:
            for k in range(max(0, i - LOOK_BACK_MS // FRAME_MS), i):
                if quiet[k] or db[k] < loud - AUDIBLE_UNDER_DB:
                    continue
                c = k * step + step // 2
                w = y[max(0, c - half):c + half]
                if _aperiodicity(w, ANALYSIS_RATE) > APERIODIC and _low_share(w, ANALYSIS_RATE) > LOW_SHARE:
                    flags[k] = True
        i = j
    return flags


def soften_creak(x: np.ndarray, rate: int, setting: str) -> np.ndarray:
    """`x` (frames x channels, float) with its phrase-end creak softened as
    CREAKS[setting] says; any other setting returns it untouched."""
    gains = CREAKS.get(setting)
    if gains is None or not len(x):
        return x
    flags = creak_frames(x.mean(axis=1), rate)
    if not flags.any():
        return x
    step = rate * FRAME_MS // 1000
    mask = np.zeros(len(x))
    on = np.repeat(flags, step)[:len(x)]
    mask[:len(on)] = on
    ramp = max(1, rate * RAMP_MS // 1000)
    mask = np.convolve(mask, np.ones(ramp) / ramp, mode="same")   # 0..1, ramped
    low_gain = 1 + mask * (10 ** (gains[0] / 20) - 1)
    full_gain = 1 + mask * (10 ** (gains[1] / 20) - 1)
    low = sosfiltfilt(butter(4, LOW_HZ, "low", fs=rate, output="sos"), x, axis=0)
    return ((x - low) + low * low_gain[:, None]) * full_gain[:, None]
