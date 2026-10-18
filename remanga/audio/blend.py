"""Noise blended into the voice: a faint, breathy grain that follows the
voice everywhere it goes, so it is felt rather than heard.

A TTS voice is perfectly clean - every harmonic exact, nothing in between -
and a real voice never is: breath and air ride on it, shaped by the same
mouth. A hiss laid under the voice is heard as a layer (user, 2026-10-18,
on the phone effect: "the noise isn't blended"); this is noise made FROM
the voice instead (user request, 2026-10-18: "a small amount of noise that
blends with vocal, not noticeable but can be felt"):

    random-phase noise whose spectrum, frame by frame, is the voice's own
    spectral envelope - smoothed across frequency so it carries the voice's
    tone and loudness but none of its pitch - mixed this far under it.

So it rises and falls with every syllable, is brightest where the voice is
bright, and is silent in the pauses; under the voice it sits in exactly
the bands the voice masks. `audio.voice_blended_noise_db`: how far under the
voice, 0 = off. Added before the voice chain (audio/voice_chain.py), as
anything a mic hears is."""

from __future__ import annotations

import numpy as np
from scipy import signal

# Frames: ~23 ms at 44.1 kHz, a quarter hop.
FFT_SIZE = 1024
HOP_SIZE = 256
# The envelope: the voice's magnitude averaged over this many Hz (wide enough
# that harmonics - and so pitch - do not come through) and this many frames.
SMOOTH_HZ = 600
SMOOTH_FRAMES = 3
# Processed in blocks this long, with this much context either side, so a
# whole chapter never sits in memory as one spectrogram.
BLOCK_S = 30
CONTEXT_S = 1

_SEED = 23


def _voice_shaped_noise(voice: np.ndarray, sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    """Noise with `voice`'s smoothed spectral envelope, frame by frame."""
    stft = {"fs": sample_rate, "nperseg": FFT_SIZE, "noverlap": FFT_SIZE - HOP_SIZE}
    _, _, spec = signal.stft(voice, **stft)
    bins = max(1, round(SMOOTH_HZ / (sample_rate / FFT_SIZE)))
    kernel = np.ones((bins, SMOOTH_FRAMES), dtype=np.float32) / (bins * SMOOTH_FRAMES)
    envelope = signal.oaconvolve(np.abs(spec).astype(np.float32), kernel, mode="same")
    _, _, white = signal.stft(rng.standard_normal(len(voice)).astype(np.float32), **stft)
    white /= np.sqrt(np.mean(np.abs(white) ** 2)) or 1.0
    _, noise = signal.istft(white * np.maximum(envelope, 0), **stft)
    return noise[: len(voice)]


def blend_noise(x: np.ndarray, sample_rate: int, under_db: float) -> np.ndarray:
    """`x` (frames x channels, float) with voice-shaped noise `under_db` under
    it (overall RMS against overall RMS - it follows the voice, so the gap is
    the same in every word)."""
    if under_db <= 0:
        return x
    voice = x.mean(axis=1)
    rng = np.random.default_rng(_SEED)
    block, context = sample_rate * BLOCK_S, sample_rate * CONTEXT_S
    noise = np.zeros(len(voice), dtype=np.float32)
    for start in range(0, len(voice), block):
        lo, hi = max(0, start - context), min(len(voice), start + block + context)
        piece = _voice_shaped_noise(voice[lo:hi], sample_rate, rng)
        keep = min(block, len(voice) - start)
        noise[start: start + keep] = piece[start - lo: start - lo + keep]
    voice_rms, noise_rms = np.sqrt(np.mean(voice ** 2)), np.sqrt(np.mean(noise ** 2))
    if voice_rms <= 0 or noise_rms <= 0:
        return x
    return x + (noise * (voice_rms / noise_rms * 10 ** (-under_db / 20)))[:, None]
