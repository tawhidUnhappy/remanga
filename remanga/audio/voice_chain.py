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

from remanga.audio.blend import blend_noise
from remanga.audio.breath import BREATHS, add_breath
from remanga.audio.creak import CREAKS, soften_creak
from remanga.audio.master import integrated_loudness
from remanga.audio.microphone import MICROPHONES, mic_filters, place_in_room, read_wav, speech_level, write_wav
from remanga.audio.phone import RECORDINGS, phone_filters, record_on_phone, through_codec
from remanga.config import AudioConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg

# Bumped whenever the chain makes something different from the same
# settings, so a mix built the old way is not taken as up to date.
VOICE_CHAIN_VERSION = 2

# Where the bass shelf sits: the 100-200 Hz chest of a voice. Under 60 Hz is
# rumble rather than voice, so it is cut instead of boosted along with it.
#
# A Butterworth shelf (Q 0.707), never one set by octave width: measured with
# tones, version 1's `t=o:w=1` shelf at 150 Hz boosted 100 Hz by 7 dB but CUT
# 200 Hz by 2.4 dB - exactly where a voice's fundamental sits - so on real
# narration the "bass boost" came out about 1 dB quieter instead of deeper.
BASS_SHELF_HZ = 180
BASS_SHELF_Q = 0.707
RUMBLE_CUT_HZ = 60

# Where the presence boost sits: the 3-5 kHz band that carries a voice's
# consonants and edge - lifting it makes the voice cut through and sound up
# front, the "powerful" half of a broadcast sound that bass alone muddies.
PRESENCE_HZ = 4000

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
    # The compressor first, then the EQ: put before it, the compressor pulls
    # the boosted band back down (the loud, voiced parts are the bass-heavy
    # ones), and most of the boost never reaches the mix.
    filters = []
    if config.voice_bass_boost_db > 0:
        filters.append(f"highpass=f={RUMBLE_CUT_HZ}")
    preset = COMPRESSORS.get(config.voice_compressor)
    if preset:
        if input_lufs is not None:
            filters.insert(0, f"volume={COMPRESSOR_INPUT_LUFS - input_lufs:.2f}dB")
        filters.append(f"acompressor={preset}")
    if config.voice_bass_boost_db > 0:
        filters.append(f"bass=g={config.voice_bass_boost_db:g}:f={BASS_SHELF_HZ}:t=q:w={BASS_SHELF_Q}")
    if config.voice_presence_db > 0:
        filters.append(f"equalizer=f={PRESENCE_HZ}:t=o:w=1.5:g={config.voice_presence_db:g}")
    # Last: the voice as a mic would hear it (audio/microphone.py).
    filters += mic_filters(config.voice_microphone)
    # Then what a phone does to what its mic heard (audio/phone.py).
    filters += phone_filters(config.voice_recording)
    return filters


def at_the_mic(path: Path, config: AudioConfig) -> None:
    """What reaches the mic with the voice, added to the wav at `path` in
    place: noise blended into the voice (audio/blend.py), the narrator's
    breath (audio/breath.py) and, on a phone, the hiss riding with the voice
    and the phone's codec (audio/phone.py). Before the chain, so it shapes
    them as it shapes the voice - and before all of them, the phrase-end
    creak softened (audio/creak.py), so nothing after it lifts the creak or
    builds noise from it."""
    if (config.voice_breath not in BREATHS and config.voice_recording not in RECORDINGS
            and config.voice_blended_noise_db <= 0 and config.voice_creak not in CREAKS):
        return
    seg, x = read_wav(path)
    x = soften_creak(x.astype("float64"), seg.frame_rate, config.voice_creak)
    speech = speech_level(x.mean(axis=1), seg.frame_rate)
    # First, from the voice alone - not from the breath or hiss added after.
    x = blend_noise(x, seg.frame_rate, config.voice_blended_noise_db)
    x = add_breath(x, seg.frame_rate, speech, config.voice_breath)
    x = record_on_phone(x, seg.frame_rate, speech, config.voice_recording)
    write_wav(path, seg, x)
    if config.voice_recording in RECORDINGS:
        through_codec(path)


def polish_voice(track: AudioSegment, work_dir: Path, config: AudioConfig) -> AudioSegment:
    """The narration track through the voice chain, at the loudness it came
    in at. A failed pass is a warning and the track as it was: a recap
    without the polish beats no recap."""
    if (config.voice_bass_boost_db <= 0 and config.voice_presence_db <= 0
            and config.voice_compressor not in COMPRESSORS and config.voice_microphone not in MICROPHONES
            and config.voice_breath not in BREATHS and config.voice_recording not in RECORDINGS
            and config.voice_blended_noise_db <= 0 and config.voice_creak not in CREAKS):
        return track
    raw, polished = work_dir / "voice_raw.wav", work_dir / "voice_polished.wav"
    try:
        track.export(raw, format="wav")
        before = integrated_loudness(raw)
        at_the_mic(raw, config)
        filters = voice_filters(config, before)
        console.print(f"[cyan]Voice chain:[/] [dim]{_esc(', '.join(filters))}[/]")
        run_ffmpeg(["ffmpeg", "-y", "-i", str(raw), "-af", ",".join(filters), "-ar", str(config.sample_rate),
                    "-ac", str(track.channels), str(polished)], check=True, capture=True)
        place_in_room(polished, config.voice_microphone, tone=config.voice_recording not in RECORDINGS)
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
