"""Sample-rate conversion that doesn't add its own noise.

pydub's `AudioSegment.set_frame_rate()` resamples with `audioop.ratecv`,
which is plain linear interpolation with no anti-imaging filter at all.
That is fine for a rough preview and audibly wrong for anything anyone
listens to: upsampling IndexTTS-2.5's native 22.05 kHz output to the
project's 44.1 kHz mirrors the whole signal back down around the source's
old 11.025 kHz Nyquist point, and the mirror is not subtle. Measured on a
finished narration clip from this repo:

    8000-11000 Hz  mean -69.8 dB   <- real speech
    11000-11500 Hz mean -95.6 dB   <- the notch at the old Nyquist
    11500-16000 Hz mean -68.2 dB   <- the mirror image, LOUDER than the
                                      real content it is folded from

Speech has essentially nothing up there, so that entire band is invented -
a metallic, gritty edge laid over every clip, which is exactly the "glitchy
/ artifact" character the narration had. ffmpeg's soxr resampler filters
properly and the images simply aren't there.

`load_audio` is the way the pipeline should open any file it also needs at
a different rate. It only shells out when a conversion is actually needed,
so re-reading a clip that is already at the target rate (most of what
audio/mix.py does) stays a plain pydub load with no subprocess at all.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pydub import AudioSegment

from remanga.ffmpeg_io import run_ffmpeg

# soxr's precision in bits. 28 is its "high quality" tier - far below the
# cost that would matter here (a few ms on a 7-second clip) and well past
# the point where the resampler contributes anything audible.
_SOXR_PRECISION = 28


def load_audio(path: Path, sample_rate: int, channels: int) -> AudioSegment:
    """Loads `path` as an AudioSegment at exactly `sample_rate`/`channels`,
    resampling through ffmpeg's soxr rather than pydub's linear
    interpolation when the rate has to change (see the module docstring for
    what that costs). A file already at the target rate is returned as a
    straight pydub load - channel count alone is left to pydub, since
    mono/stereo conversion is duplication or averaging and invents nothing."""
    segment = AudioSegment.from_file(path)
    if segment.frame_rate != sample_rate:
        segment = _ffmpeg_resample(path, sample_rate)
    if segment.channels != channels:
        segment = segment.set_channels(channels)
    return segment


def _ffmpeg_resample(path: Path, sample_rate: int) -> AudioSegment:
    """`path` resampled to `sample_rate` via soxr, returned as an
    AudioSegment. Falls back to pydub's own resampler if ffmpeg isn't
    usable for some reason - a slightly gritty clip is a better outcome
    than a chapter that won't render at all."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "resampled.wav"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(path),
            "-af", f"aresample=resampler=soxr:precision={_SOXR_PRECISION}",
            "-ar", str(sample_rate),
            str(out_path),
        ]
        try:
            run_ffmpeg(cmd, check=True, capture=True)
            return AudioSegment.from_file(out_path)
        except Exception:
            return AudioSegment.from_file(path).set_frame_rate(sample_rate)
