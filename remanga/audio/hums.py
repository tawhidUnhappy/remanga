"""Voice in a take that is not a word.

Qwen3-TTS samples every frame of a take, and now and then it loses its place
between two sentences and holds a note instead: a moan or hum as loud as the
narration around it, pitched like the voice, saying nothing. The take is
otherwise fine - every word of the script is in it, the alignment matches,
the length is right - so nothing that checks the take as a whole ever sees
it. It is audible in the video as an artifact between two words.

Measured on the one reported (HimeSama ch1, 2026-09-29): after "family." the
take went silent for 0.6s and then produced 1.2s at -22 dB, centroid ~450 Hz,
spectral flatness 0.01 - the numbers of a voiced vowel - with no word in it
for whisper to find. Swept over 27 real takes (two projects), a 0.3s run of
such frames inside a gap between whisper's words fired on that one and on
nothing else: a pause is quiet, a breath is noisy (flatness well above 0.05),
and a word is a word."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from remanga.audio.resample import load_audio

RATE = 16000
HOP_SECONDS = 0.02

# How far under the take's typical word a frame may be and still count as
# voice. The hum measured 5 dB ABOVE the take's speech median, a pause 30 dB
# below it.
BELOW_SPEECH_DB = 12.0

# Spectral flatness under which a frame is tonal - a voice, not a breath or
# the noise floor. Voiced speech measured 0.007-0.03, the silence around the
# hum 0.1-0.18.
MAX_FLATNESS = 0.05

# Whisper's word edges are loose by a frame or two; this much of each gap's
# ends is left to the words either side of it.
EDGE_SECONDS = 0.06

# The shortest run of voice with no word in it that is reported. The measured
# hum ran 0.68s under these rules; nothing in 26 clean takes reached 0.2s.
MIN_RUN_SECONDS = 0.3


@dataclass(frozen=True)
class Hum:
    start: float
    end: float
    after: str
    before: str

    @property
    def seconds(self) -> float:
        return self.end - self.start

    def describe(self) -> str:
        return f"{self.start:.1f}-{self.end:.1f}s, between '{self.after}' and '{self.before}'"


def _frames(clip: Path) -> tuple[np.ndarray, np.ndarray]:
    """Loudness (dB) and spectral flatness of every 20ms hop of `clip`."""
    # load_audio, not pydub's set_frame_rate: its unfiltered resampling folds
    # the top of the spectrum down into noise, which reads as flatness here.
    audio = load_audio(clip, RATE, channels=1)
    x = np.array(audio.get_array_of_samples(), dtype=np.float32) / float(1 << (8 * audio.sample_width - 1))
    hop = int(HOP_SECONDS * RATE)
    window = 2 * hop
    count = max(0, (len(x) - window) // hop)
    if count == 0:
        return np.zeros(0), np.zeros(0)
    idx = np.arange(window)[None, :] + hop * np.arange(count)[:, None]
    frames = x[idx]
    rms_db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(window), axis=1)) + 1e-9
    flatness = np.exp(np.log(spectrum).mean(axis=1)) / spectrum.mean(axis=1)
    return rms_db, flatness


def find_hums(clip: Path, words: list[dict[str, Any]]) -> list[Hum]:
    """Every stretch of `clip` that sounds like voice where whisper heard no
    word. `words` is the transcript's word list (start/end in seconds)."""
    words = [w for w in words if w.get("end", 0) > w.get("start", 0)]
    if not words:
        return []
    rms_db, flatness = _frames(clip)
    if len(rms_db) == 0:
        return []

    def span(a: float, b: float) -> slice:
        return slice(int(a / HOP_SECONDS), int(b / HOP_SECONDS))

    levels = [rms_db[span(w["start"], w["end"])].mean() for w in words
              if len(rms_db[span(w["start"], w["end"])])]
    speech_db = float(np.median(levels))
    voiced = (rms_db > speech_db - BELOW_SPEECH_DB) & (flatness < MAX_FLATNESS)

    duration = len(rms_db) * HOP_SECONDS
    edges = [0.0] + [e for w in words for e in (w["start"], w["end"])] + [duration]
    labels = ["(start)"] + [w["word"].strip() for w in words] + ["(end)"]
    hums: list[Hum] = []
    for i in range(0, len(edges), 2):
        a, b = edges[i] + EDGE_SECONDS, edges[i + 1] - EDGE_SECONDS
        if b - a < MIN_RUN_SECONDS:
            continue
        run_start = None
        gap = voiced[span(a, b)]
        for j, on in enumerate(np.append(gap, False)):
            if on and run_start is None:
                run_start = j
            elif not on and run_start is not None:
                if (j - run_start) * HOP_SECONDS >= MIN_RUN_SECONDS:
                    hums.append(Hum(a + run_start * HOP_SECONDS, a + j * HOP_SECONDS,
                                    after=labels[i // 2], before=labels[i // 2 + 1]))
                run_start = None
    return hums
