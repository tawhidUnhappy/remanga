"""Making the narration sound recorded rather than generated: the voice
through a broadcast mic, in a small room, with the room's own faint air.

A TTS voice is recorded nowhere - no room around it, dead digital silence
between words, a perfectly flat response - and the ear hears that as
artificial however natural the voice is (user report, 2026-10-18: "too
smooth"). A real recording always has all three, so `audio.voice_microphone`
puts them back, at mix time, over the narration only (audio/voice_chain.py):

    close   a close-talking dynamic mic: its EQ shape, a little drive, the
            room tone - no audible room
    studio  the same, plus a small treated room's early reflections and
            short tail around the voice

The mic's EQ and drive are ffmpeg filters (mic_filters, run with the rest of
the chain); the room and the room tone are made here, on the samples."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pydub import AudioSegment
from scipy import signal

MICROPHONES = ("close", "studio")

# A broadcast dynamic mic's shape: the proximity warmth of talking close,
# its presence peak, and the gentle fall above it that keeps it from
# sounding hi-fi. Then a little drive - the soft harmonics of a mic preamp
# pushed by a voice - pre-gained into a tanh curve and back.
_MIC_EQ = ["highpass=f=80",
           "equalizer=f=250:t=q:w=1.0:g=1.5",
           "equalizer=f=5500:t=q:w=1.5:g=2",
           "equalizer=f=10000:t=q:w=0.8:g=-3"]
_DRIVE_DB = 6.0

# The room: a small treated room. RT60 0.22 s, the first reflection 3 ms
# after the voice, its tail darker than the voice (walls soak up the
# highs), mixed this far under the direct sound.
ROOM_RT60_S = 0.22
ROOM_PREDELAY_MS = 3
ROOM_WET_DB = -16.0

# The room tone: what a real mic hears when nobody talks - low air and a
# little hiss, this far under the voice's loudness. Quiet enough to go
# unnoticed under speech; it is what makes the pauses sound like a room
# rather than like nothing.
ROOM_TONE_UNDER_DB = 56.0

# Fixed seeds: the same chapter mixed twice is the same file.
_ROOM_SEED, _TONE_SEED = 7, 11


def mic_filters(style: str) -> list[str]:
    """The ffmpeg part of a microphone: its EQ, then its drive."""
    if style not in MICROPHONES:
        return []
    return [*_MIC_EQ, f"volume={_DRIVE_DB:g}dB", "asoftclip=type=tanh", f"volume={-_DRIVE_DB:g}dB"]


def room_impulse(sample_rate: int) -> np.ndarray:
    """A small room's reflections and tail (the direct sound not included):
    decaying noise, darkened, after a short pre-delay."""
    rng = np.random.default_rng(_ROOM_SEED)
    length = int(sample_rate * ROOM_RT60_S * 1.5)
    t = np.arange(length) / sample_rate
    tail = rng.standard_normal(length) * np.exp(-6.91 * t / ROOM_RT60_S)  # -60 dB at RT60
    b, a = signal.butter(2, 5000 / (sample_rate / 2), "low")
    tail = signal.lfilter(b, a, tail)
    tail = np.concatenate([np.zeros(int(sample_rate * ROOM_PREDELAY_MS / 1000)), tail])
    # Scaled so the tail carries ROOM_WET_DB of the direct sound's energy.
    return tail / np.sqrt(np.sum(tail ** 2)) * 10 ** (ROOM_WET_DB / 20)


def room_tone(frames: int, sample_rate: int, level_rms: float) -> np.ndarray:
    """Room tone at `level_rms`: pink-ish noise, mostly low air with a soft hiss."""
    rng = np.random.default_rng(_TONE_SEED)
    white = rng.standard_normal(frames)
    # Paul Kellet's economy pink filter, as a 3-pole IIR.
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    pink = signal.lfilter(b, a, white)
    hb, ha = signal.butter(2, 60 / (sample_rate / 2), "high")  # no subsonic rumble
    lb, la = signal.butter(2, 9000 / (sample_rate / 2), "low")
    tone = signal.lfilter(lb, la, signal.lfilter(hb, ha, pink))
    return tone / (np.sqrt(np.mean(tone ** 2)) or 1.0) * level_rms


def read_wav(path: Path) -> tuple[AudioSegment, np.ndarray]:
    """The wav at `path` and its samples (frames x channels, float, full scale 1)."""
    seg = AudioSegment.from_file(path)
    full = float(1 << (8 * seg.sample_width - 1))
    return seg, np.array(seg.get_array_of_samples(), dtype=np.float32).reshape(-1, seg.channels) / full


def write_wav(path: Path, seg: AudioSegment, x: np.ndarray) -> None:
    """`x` written over the wav at `path`, in `seg`'s format."""
    full = float(1 << (8 * seg.sample_width - 1))
    ints = np.clip(np.round(x * full), -full, full - 1).astype({2: np.int16, 4: np.int32}[seg.sample_width])
    seg._spawn(ints.reshape(-1).tobytes()).export(path, format="wav")


def speech_level(mono: np.ndarray, sample_rate: int) -> float:
    """The voice's RMS over its loud half (speech, not the pauses)."""
    frame = max(1, sample_rate // 50)
    usable = len(mono) // frame * frame
    rms = np.sqrt(np.mean(mono[:usable].reshape(-1, frame) ** 2, axis=1)) if usable else np.array([0.0])
    return float(np.sqrt(np.mean(np.square(rms[rms >= np.median(rms)])))) if rms.size else 0.0


def place_in_room(path: Path, style: str, tone: bool = True) -> None:
    """The room (studio) and the room tone (both) added to the wav at `path`,
    in place. The tone is set from the voice's own level, so it sits the
    same distance under every chapter. No tone when a phone's gate has
    already made the pauses black (audio/phone.py) - it would fill them."""
    if style not in MICROPHONES:
        return
    seg, x = read_wav(path)
    mono = x.mean(axis=1)
    if style == "studio":
        wet = signal.oaconvolve(mono, room_impulse(seg.frame_rate).astype(np.float32))[: len(mono)]
        x = x + wet[:, None]
    speech = speech_level(mono, seg.frame_rate)
    if tone and speech > 0:
        x = x + room_tone(len(x), seg.frame_rate, speech * 10 ** (-ROOM_TONE_UNDER_DB / 20))[:, None]
    write_wav(path, seg, x)
