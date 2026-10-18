"""The narration as a phone (or a noise-removal app) records it: a bright
hiss that rides with the voice, then the voice codec it is saved or sent in.

Matched to the user's reference (user request, 2026-10-18: "noise removing
after a blend of voice and some kinda noise") - a 4.6-hour recap narration
whose zoomed spectrogram shows it plainly: while the voice is on, an even
hiss from about 3 to 12 kHz rides with it and buries its sibilants; when it
stops, the hiss is gone; the top is a haze that swells with every syllable
and stops flat at 12 kHz, with the codec's band seams across it. The voice
is darker than a TTS voice and has nothing over 12 kHz.

What did not work, and why it is not here:
- a Wiener suppressor (version 1): a faint hiss carpet through the pauses,
  nothing that came and went with the words - "this one is not it";
- a hard gate (version 2): voice and hiss cut off at every word end, and a
  mains hum it left exposed in each short pause - together a low "dum"
  after the words, and the hiss heard as a layer switching on and off -
  "like drum, not natural ... the noise isn't blended".

So the hiss now follows the voice's own loudness smoothly (follow_voice):
it swells and fades with the words like part of the voice rather than a
layer, and the voice itself is never cut.

    hiss    white-ish noise above ~2.5 kHz (room_noise), its level following
            the voice (follow_voice)
    tone    the voice darker (before the hiss); no lows, last in the voice
            chain (phone_filters)
    codec   Opus at 24 kbps, as voice apps send it (through_codec)

`audio.voice_recording`: "off" or "phone"."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import signal

from remanga.audio.microphone import read_wav, write_wav
from remanga.ffmpeg_io import run_ffmpeg

RECORDINGS = ("phone",)

# The hiss, this far under the speech level (RMS of its loud half, as in
# audio/microphone.py), and how far its level wanders over seconds. Set so
# the 5-10 kHz haze under the words matches the reference's.
HISS_UNDER_DB = 37.0
HISS_WOBBLE_DB = 1.5

# How the hiss follows the voice (5 ms frames): its level tracks the voice's,
# rising within HISS_ATTACK_MS and falling over HISS_RELEASE_MS - slow enough
# to fade with a word's tail, never a cut - and never under HISS_FLOOR_DB of
# its level while talking, so the pauses keep the faintest air.
FRAME_MS = 5
HISS_ATTACK_MS = 10
HISS_RELEASE_MS = 90
HISS_FLOOR_DB = -24.0

# A phone mic: the voice darker above 5.5 kHz - before the hiss goes in,
# since the hiss is the phone's own and never passed through its mic - and
# no low end; last, the codec's 12 kHz edge put back as a cliff (twice), since
# the mic's drive after it grows a little above.
DARKER_HZ = 5500
DARKER_DB = -3.0
_PHONE_EQ = ["highpass=f=110", "lowpass=f=12000", "lowpass=f=12000"]

# The codec the phone saves or sends it with: Opus as voice apps use it.
# At this rate it stops at 12 kHz and refills the top from the voice's own
# band energies - the haze that swells with every syllable, and the fixed
# band seams across it, both plain in the reference. Measured: no delay,
# same length, -0.2 dB. CODEC_HEADROOM_DB keeps its overshoot off 0 dBFS
# in the 16-bit wav it comes back as; it is given back afterwards.
CODEC = ["-c:a", "libopus", "-b:a", "24k", "-application", "voip"]
CODEC_HEADROOM_DB = 6.0

_SEED = 17


def phone_filters(style: str) -> list[str]:
    """The ffmpeg part of a phone: its tone."""
    return list(_PHONE_EQ) if style in RECORDINGS else []


def _wander(frames: int, sample_rate: int, depth_db: float, rng: np.random.Generator) -> np.ndarray:
    """A gain wandering +-depth_db over seconds (smoothed random steps)."""
    step = sample_rate // 10
    knots = np.convolve(rng.uniform(-1, 1, frames // step + 2), np.ones(8) / 8, mode="same")
    return 10 ** (np.interp(np.arange(frames) / step, np.arange(len(knots)), knots) * depth_db / 20)


def room_noise(frames: int, sample_rate: int, level_rms: float) -> np.ndarray:
    """The hiss at `level_rms`: white noise above ~2.5 kHz, a touch of pink
    under it, stopping at 13 kHz (the phone's lowpass takes it from there)."""
    rng = np.random.default_rng(_SEED)
    white = rng.standard_normal(frames)
    hb, ha = signal.butter(2, 2500 / (sample_rate / 2), "high")
    lb, la = signal.butter(4, 13000 / (sample_rate / 2), "low")
    pink = signal.lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786],
                          [1, -2.494956002, 2.017265875, -0.522189400], rng.standard_normal(frames))
    noise = signal.lfilter(hb, ha, white) + 0.3 * pink / (np.std(pink) or 1.0)
    noise = signal.lfilter(lb, la, noise) * _wander(frames, sample_rate, HISS_WOBBLE_DB, rng)
    return noise / (np.sqrt(np.mean(noise ** 2)) or 1.0) * level_rms


def follow_voice(voice: np.ndarray, sample_rate: int, speech_rms: float) -> np.ndarray:
    """Per-sample gain for the hiss: the voice's own level (5 ms frames)
    against the speech level, capped at 1, rising fast and falling slowly,
    never under HISS_FLOOR_DB."""
    frame = max(1, sample_rate * FRAME_MS // 1000)
    n = -(-len(voice) // frame)
    padded = np.zeros(n * frame, dtype=np.float32)
    padded[: len(voice)] = voice
    level = np.minimum(np.sqrt(np.mean(padded.reshape(n, frame) ** 2, axis=1)) / speech_rms, 1.0)
    rise, fall = np.exp(-FRAME_MS / HISS_ATTACK_MS), np.exp(-FRAME_MS / HISS_RELEASE_MS)
    gains = np.empty(n, dtype=np.float32)
    now = 0.0
    for i, target in enumerate(level):
        coef = rise if target > now else fall
        now = coef * now + (1 - coef) * target
        gains[i] = now
    gains = np.maximum(gains, 10 ** (HISS_FLOOR_DB / 20))
    centers = (np.arange(n) + 0.5) * frame
    return np.interp(np.arange(len(voice)), centers, gains).astype(np.float32)


def high_shelf(sample_rate: int, hz: float, gain_db: float) -> tuple[np.ndarray, np.ndarray]:
    """A high shelf biquad (RBJ cookbook, slope 1)."""
    a_ = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * hz / sample_rate
    cos, alpha = np.cos(w0), np.sin(w0) / 2 * np.sqrt(2)
    root = 2 * np.sqrt(a_) * alpha
    b = [a_ * ((a_ + 1) + (a_ - 1) * cos + root), -2 * a_ * ((a_ - 1) + (a_ + 1) * cos),
         a_ * ((a_ + 1) + (a_ - 1) * cos - root)]
    a = [(a_ + 1) - (a_ - 1) * cos + root, 2 * ((a_ - 1) - (a_ + 1) * cos), (a_ + 1) - (a_ - 1) * cos - root]
    return np.array(b) / a[0], np.array(a) / a[0]


def record_on_phone(x: np.ndarray, sample_rate: int, speech_rms: float, style: str) -> np.ndarray:
    """`x` (frames x channels, float) as a phone's mic hears it: the voice a
    little darker, the hiss riding with it. Same length, no delay."""
    if style not in RECORDINGS or speech_rms <= 0:
        return x
    gain = follow_voice(x.mean(axis=1), sample_rate, speech_rms)
    x = signal.lfilter(*high_shelf(sample_rate, DARKER_HZ, DARKER_DB), x, axis=0).astype(np.float32)
    hiss = room_noise(len(x), sample_rate, speech_rms * 10 ** (-HISS_UNDER_DB / 20)).astype(np.float32)
    return x + (hiss * gain)[:, None]


def through_codec(path: Path) -> None:
    """The wav at `path`, in place, as the phone's codec gives it back."""
    coded, back = path.with_suffix(".opus"), path.with_name(f"{path.stem}_decoded.wav")
    try:
        seg, x = read_wav(path)
        run_ffmpeg(["ffmpeg", "-y", "-i", str(path), "-ac", "1", "-af", f"volume={-CODEC_HEADROOM_DB:g}dB",
                    *CODEC, str(coded)], check=True, capture=True)
        run_ffmpeg(["ffmpeg", "-y", "-i", str(coded), "-ar", str(seg.frame_rate), "-ac", str(seg.channels),
                    "-c:a", "pcm_s16le", str(back)], check=True, capture=True)
        _, y = read_wav(back)
        # Exactly as long as it went in, so the video keeps its timing.
        y = np.pad(y, ((0, max(0, len(x) - len(y))), (0, 0)))[: len(x)]
        write_wav(path, seg, y * 10 ** (CODEC_HEADROOM_DB / 20))
    finally:
        coded.unlink(missing_ok=True)
        back.unlink(missing_ok=True)
