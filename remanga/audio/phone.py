"""The narration as a phone records it: the room's background noise picked
up with the voice, then the phone's own noise removal run over the lot.

That second step is what gives a phone (or app-denoised) voice its sound -
not the noise itself but what removing it leaves: a faint, slightly watery
residue under the words that the suppressor can't take out, near-silence in
the pauses, and the small mic's band-limited, bright tone (user request,
2026-10-18: "noise removing after a blend of voice and some kinda noise").
So it is done for real, not imitated: noise is mixed under the voice, then
a phone-style suppressor takes it out again (record_on_phone) - a Wiener
gain per frequency and frame, smoothed the decision-directed way phones do
it, over the noise level it learned. Where speech and noise are close, the
gain flickers bin by bin and leaves the watery residue; under the words it
lets the noise through, in the pauses it pulls it down. That happens
before the voice chain, as a phone recording reaches the editor: the
chain's compressor then lifts the residue a little, as it would. The tone
(phone_filters) runs last in the chain.

No ffmpeg filter does the suppressing: afftdn delays the audio 25 ms (the
video would drift off the words) and barely touched this noise (2 dB).

`audio.voice_recording`: "off" or "phone"."""

from __future__ import annotations

import numpy as np
from scipy import signal

RECORDINGS = ("phone",)

# The room the phone hears: pink air and a low fan/traffic band, this far
# under the speech level, breathing slowly up and down.
NOISE_UNDER_DB = 30.0
NOISE_WOBBLE_DB = 2.0

# The phone's suppressor: frames of FFT_SIZE with HOP_SIZE between them; at
# most this much reduction (a deeper floor sounds dead, then gated);
# DD_SMOOTHING is how much of the last frame's estimate carries over - 0.98
# is studio-smooth, lower leaves more of the flicker phones are known for.
FFT_SIZE = 1024
HOP_SIZE = 256
FLOOR_DB = -20.0
DD_SMOOTHING = 0.9
# Processed in blocks this long, with this much context either side, so a
# whole chapter never sits in memory as one spectrogram.
BLOCK_S = 30
CONTEXT_S = 1
# A phone's small electret mic: no low end, a bright bump, and the top
# trimmed by its voice-memo encoder.
_PHONE_EQ = ["highpass=f=110",
             "equalizer=f=3000:t=q:w=1.2:g=2",
             "lowpass=f=11500"]

_SEED = 17


def phone_filters(style: str) -> list[str]:
    """The ffmpeg part of a phone: its tone."""
    return list(_PHONE_EQ) if style in RECORDINGS else []


def room_noise(frames: int, sample_rate: int, level_rms: float) -> np.ndarray:
    """A lived-in room's background at `level_rms`: pink air, a band of low
    fan rumble, its level wandering a little over seconds."""
    rng = np.random.default_rng(_SEED)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]  # Kellet's pink filter
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    pink = signal.lfilter(b, a, rng.standard_normal(frames))
    fb, fa = signal.butter(2, [120 / (sample_rate / 2), 500 / (sample_rate / 2)], "band")
    fan = signal.lfilter(fb, fa, rng.standard_normal(frames))
    noise = pink / (np.std(pink) or 1.0) + 0.6 * fan / (np.std(fan) or 1.0)
    hb, ha = signal.butter(2, 50 / (sample_rate / 2), "high")
    noise = signal.lfilter(hb, ha, noise)
    # The slow wander: smoothed random steps, in dB.
    step = sample_rate // 10
    knots = rng.uniform(-1, 1, frames // step + 2)
    knots = np.convolve(knots, np.ones(8) / 8, mode="same")
    wobble = np.interp(np.arange(frames) / step, np.arange(len(knots)), knots)
    noise *= 10 ** (wobble * NOISE_WOBBLE_DB / 20)
    return noise / (np.sqrt(np.mean(noise ** 2)) or 1.0) * level_rms


def _suppress(noisy: np.ndarray, noise_power: np.ndarray) -> np.ndarray:
    """Wiener gains for a block's spectrogram (bins x frames), decision-
    directed (Ephraim-Malah) over its frames. It settles within a few
    frames, well inside the block's context."""
    floor = 10 ** (FLOOR_DB / 20)
    power = np.abs(noisy) ** 2
    gains = np.empty(power.shape, dtype=np.float32)
    prior = np.zeros(power.shape[0], dtype=np.float32)
    for i in range(power.shape[1]):
        post = power[:, i] / noise_power
        snr = DD_SMOOTHING * prior / noise_power + (1 - DD_SMOOTHING) * np.maximum(post - 1, 0)
        gain = np.maximum(snr / (1 + snr), floor)
        gains[:, i] = gain
        prior = gain ** 2 * power[:, i]
    return gains


def record_on_phone(x: np.ndarray, sample_rate: int, speech_rms: float, style: str) -> np.ndarray:
    """`x` (frames x channels, float) as a phone records it: the room's noise
    under it, then the phone's suppressor over both. Same length, no delay."""
    if style not in RECORDINGS or speech_rms <= 0:
        return x
    noise = room_noise(len(x), sample_rate, speech_rms * 10 ** (-NOISE_UNDER_DB / 20)).astype(np.float32)
    noisy = x + noise[:, None]
    stft = {"fs": sample_rate, "nperseg": FFT_SIZE, "noverlap": FFT_SIZE - HOP_SIZE}
    block, context = sample_rate * BLOCK_S, sample_rate * CONTEXT_S
    out = np.empty_like(noisy)
    for start in range(0, len(noisy), block):
        lo, hi = max(0, start - context), min(len(noisy), start + block + context)
        # What the phone learned the room sounds like: this stretch's noise.
        _, _, room = signal.stft(noise[lo:hi], **stft)
        noise_power = np.mean(np.abs(room) ** 2, axis=1) + 1e-20
        _, _, spec = signal.stft(noisy[lo:hi].mean(axis=1), **stft)
        gains = _suppress(spec, noise_power)
        for channel in range(noisy.shape[1]):
            _, _, chan = signal.stft(noisy[lo:hi, channel], **stft)
            _, clean = signal.istft(chan * gains, **stft)
            piece = clean[start - lo: start - lo + min(block, len(noisy) - start)]
            out[start: start + len(piece), channel] = piece
    return out
