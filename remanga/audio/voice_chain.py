"""The narrator's voice chain: a bass shelf and a compressor over the whole
narration track, before the music goes under it - see audio/mix.py.

Applied at mix time, never baked into the clips: it is how the chapter
sounds, not what was synthesized, so changing it costs a re-mix and never
narrating again. The chain does not change the track's length, so the video's
timeline is untouched.

The loudness stays where it was: the compressor takes level off the peaks,
and the chain puts back exactly what it took (measured), so turning it on or
off changes the voice's character and never its level - the final loudness
pass (audio/master.py:write_master) is what sets that."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from remanga.audio.master import integrated_loudness
from remanga.config import AudioConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg

# Bumped whenever the chain makes something different from the same
# settings, so a mix built the old way is not taken as up to date.
VOICE_CHAIN_VERSION = 1

# Where the bass shelf sits: the 100-200 Hz chest of a voice. Under 60 Hz is
# rumble rather than voice, so it is cut instead of boosted along with it.
BASS_SHELF_HZ = 150
RUMBLE_CUT_HZ = 60

# The compressor's input is set to this loudness first, so a preset's
# threshold means the same thing whatever level the engine reads at (Kokoro
# comes back about -26 LUFS with peaks near 0 dBFS - a 25 dB crest).
COMPRESSOR_INPUT_LUFS = -20.0

# Measured on a real Kokoro chapter (af_heart, 18 min, 24.8 dB crest at the
# input): gentle leaves a 22.7 dB crest, medium 20.4, strong 17.7.
COMPRESSORS = {
    "gentle": "threshold=-22dB:ratio=2:attack=10:release=250:knee=6",
    "medium": "threshold=-26dB:ratio=3:attack=5:release=150:knee=6",
    "strong": "threshold=-32dB:ratio=6:attack=2:release=100:knee=4",
}


def voice_filters(config: AudioConfig, input_lufs: float | None) -> list[str]:
    """The ffmpeg filters the chain runs, in order - empty when it is all off."""
    filters = []
    if config.voice_bass_boost_db > 0:
        filters += [f"highpass=f={RUMBLE_CUT_HZ}",
                    f"bass=g={config.voice_bass_boost_db:g}:f={BASS_SHELF_HZ}:t=o:w=1"]
    preset = COMPRESSORS.get(config.voice_compressor)
    if preset:
        if input_lufs is not None:
            filters.insert(0, f"volume={COMPRESSOR_INPUT_LUFS - input_lufs:.2f}dB")
        filters.append(f"acompressor={preset}")
    return filters


def polish_voice(track: AudioSegment, work_dir: Path, config: AudioConfig) -> AudioSegment:
    """The narration track through the voice chain, at the loudness it came
    in at. A failed pass is a warning and the track as it was: a recap
    without the polish beats no recap."""
    if config.voice_bass_boost_db <= 0 and config.voice_compressor not in COMPRESSORS:
        return track
    raw, polished = work_dir / "voice_raw.wav", work_dir / "voice_polished.wav"
    try:
        track.export(raw, format="wav")
        before = integrated_loudness(raw)
        filters = voice_filters(config, before)
        console.print(f"[cyan]Voice chain:[/] [dim]{_esc(', '.join(filters))}[/]")
        run_ffmpeg(["ffmpeg", "-y", "-i", str(raw), "-af", ",".join(filters), "-ar", str(config.sample_rate),
                    "-ac", str(track.channels), str(polished)], check=True, capture=True)
        out = AudioSegment.from_file(polished)
        after = integrated_loudness(polished)
        if before is not None and after is not None:
            out = out + (before - after)
        return out
    except Exception as e:
        console.print(f"[yellow]The voice chain failed ({_esc(str(e))}) - mixing the voice as it was.[/]")
        return track
    finally:
        raw.unlink(missing_ok=True)
        polished.unlink(missing_ok=True)
