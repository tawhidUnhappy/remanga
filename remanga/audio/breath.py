"""The narrator's breath on the mic: the puffs of air that hit an unprotected
mic on hard consonants, and the quick inhales between sentences.

A real voice recorded close without a pop filter - or on a phone held to the
mouth - has both, and a TTS voice has neither (user request, 2026-10-18:
"the effect of breath touching microphone ... without any protection"):

    pops     at word onsets that start abruptly (the release of p/b/t/k
             and hard vowel attacks), a short toneless puff of low air
             arriving a few ms after the sound does - air is slower than sound
    inhales  a short mouth inhale filling a pause between sentences

`audio.voice_breath` picks how much: light or strong. Both are added to the
narration before the voice chain (audio/voice_chain.py), so the mic's EQ and
drive shape them as they would real air on a real mic. Nothing moves in
time: they go into pauses and onsets that are already there."""

from __future__ import annotations

import numpy as np
from scipy import signal

BREATHS = ("light", "strong")

# Per amount: the share of the candidate onsets that pop and of the pauses
# that get an inhale, and how loud each is against the speech level (RMS of
# the loud half, as in audio/microphone.py). A close mic hears an inhale
# about 25 dB under the voice; pops are low-frequency and sound quieter
# than their level.
_AMOUNTS = {
    "light": {"pop_share": 0.15, "pop_db": -10.0, "inhale_share": 0.4, "inhale_db": -30.0},
    "strong": {"pop_share": 0.35, "pop_db": -5.0, "inhale_share": 0.7, "inhale_db": -24.0},
}

# Analysis frames, and what counts as a pause / an abrupt onset, in dB
# against the speech level.
FRAME_MS = 5
QUIET_DB = -30.0
LOUD_DB = -18.0
MIN_PAUSE_MS = 30
# An onset is abrupt when it is loud this soon after the pause ends - a
# burst or a hard attack, not an "s", "h" or "m" fading in.
ABRUPT_MS = 10
# At least this long between two pops, or two inhales - never a pattern.
MIN_POP_SPACING_S = 2.5
MIN_INHALE_SPACING_S = 2.5
# The air reaches a mic a few cm away this long after the sound.
POP_DELAY_MS = 8
POP_LENGTH_MS = 60
# Inhales go in pauses at least this long, end this long before the next
# word, and last at most this long.
INHALE_MIN_GAP_MS = 120
INHALE_LEAD_MS = 25
INHALE_MAX_MS = 320

_SEED = 13


def _envelope_db(mono: np.ndarray, sample_rate: int, speech_rms: float) -> np.ndarray:
    frame = max(1, sample_rate * FRAME_MS // 1000)
    n = len(mono) // frame
    rms = np.sqrt(np.mean(mono[: n * frame].reshape(n, frame) ** 2, axis=1)) + 1e-12
    return 20 * np.log10(rms / speech_rms)


def _onsets(env: np.ndarray) -> list[tuple[int, int]]:
    """(frame the pause before it starts, frame speech starts) for every word
    that starts after a pause."""
    found, run_start, pause, armed = [], None, (0, 0), False
    for i, db in enumerate(env):
        if db < QUIET_DB:
            run_start = i if run_start is None else run_start
            continue
        if run_start is not None:
            # A quiet run long enough to be a pause; the word starts where it
            # ends, even when its first frames (an "s") are soft.
            if (i - run_start) * FRAME_MS >= MIN_PAUSE_MS:
                pause, armed = (run_start, i), True
            run_start = None
        if db >= LOUD_DB and armed:
            found.append(pause)
            armed = False
    return found


def _pop(sample_rate: int, rng: np.random.Generator) -> np.ndarray:
    """A puff of air on a capsule: a short burst of low, toneless rumble -
    1 ms attack, gone in about 40 ms. Unit RMS over its first 20 ms.

    Never a pitched thump: version 1 had a sine falling from ~100 to 40 Hz
    under the noise, which is how a kick drum is synthesized, and it was
    heard as a drum after the words (user, 2026-10-18)."""
    n = int(sample_rate * POP_LENGTH_MS / 1000)
    t = np.arange(n) / sample_rate
    env = (1 - np.exp(-t / 0.001)) * np.exp(-t / rng.uniform(0.008, 0.014))
    b, a = signal.butter(2, [40 / (sample_rate / 2), rng.uniform(300, 500) / (sample_rate / 2)], "band")
    pop = signal.lfilter(b, a, rng.standard_normal(n)) * env
    head = pop[: int(sample_rate * 0.02)]
    return pop / (np.sqrt(np.mean(head ** 2)) or 1.0)


def _inhale(sample_rate: int, length: int, rng: np.random.Generator) -> np.ndarray:
    """A mouth inhale: breathy noise with a soft peak where the mouth
    resonates, swelling and dying away. Unit RMS."""
    t = np.linspace(0, 1, length)
    env = np.sin(np.pi * t ** rng.uniform(0.7, 1.0)) ** 1.5
    b, a = signal.butter(2, [350 / (sample_rate / 2), 6000 / (sample_rate / 2)], "band")
    noise = signal.lfilter(b, a, rng.standard_normal(length))
    peak = rng.uniform(1100, 1900)
    pb, pa = signal.iirpeak(peak / (sample_rate / 2), 2.0)
    noise = noise + 1.5 * signal.lfilter(pb, pa, noise)
    breath = noise * env
    return breath / (np.sqrt(np.mean(breath ** 2)) or 1.0)


def add_breath(x: np.ndarray, sample_rate: int, speech_rms: float, amount: str) -> np.ndarray:
    """`x` (frames x channels, float) with pops and inhales added."""
    if amount not in BREATHS or speech_rms <= 0:
        return x
    settings = _AMOUNTS[amount]
    rng = np.random.default_rng(_SEED)
    mono = x.mean(axis=1)
    env = _envelope_db(mono, sample_rate, speech_rms)
    frame = max(1, sample_rate * FRAME_MS // 1000)
    out = x.copy()
    last_pop = last_inhale = -1e9
    for quiet_from, start in _onsets(env):
        at = start * frame
        # The quick inhale first: it fills the pause before this word.
        gap_ms = (start - quiet_from) * FRAME_MS
        if (gap_ms >= INHALE_MIN_GAP_MS and at - last_inhale >= MIN_INHALE_SPACING_S * sample_rate
                and rng.random() < settings["inhale_share"]):
            length = int(sample_rate * min(gap_ms - INHALE_LEAD_MS - 20, INHALE_MAX_MS) / 1000)
            end = at - int(sample_rate * INHALE_LEAD_MS / 1000)
            length = min(length, end)
            level = speech_rms * 10 ** ((settings["inhale_db"] + rng.uniform(-3, 3)) / 20)
            out[end - length: end] += (_inhale(sample_rate, length, rng) * level)[:, None]
            last_inhale = at
        # The pop: only where the word starts abruptly.
        abrupt = env[start: start + ABRUPT_MS // FRAME_MS].max(initial=-1e9) >= LOUD_DB
        if (abrupt and at - last_pop >= MIN_POP_SPACING_S * sample_rate
                and rng.random() < settings["pop_share"]):
            pop = _pop(sample_rate, rng) * speech_rms * 10 ** ((settings["pop_db"] + rng.uniform(-4, 2)) / 20)
            begin = at + int(sample_rate * POP_DELAY_MS / 1000)
            pop = pop[: max(0, len(out) - begin)]
            out[begin: begin + len(pop)] += pop[:, None]
            last_pop = at
    return out
