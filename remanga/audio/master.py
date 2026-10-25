"""Building a chapter's master audio track: the narration clips end to end,
the music bed under them, and the volume set over the result."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
from pydub import AudioSegment

from remanga.audio.clips import apply_edge_fades
from remanga.audio.resample import load_audio
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg

# Long enough to hear the music arrive and leave rather than cut, short
# enough not to swallow the first line of narration.
BGM_FADE_IN_MS = 1500
BGM_FADE_OUT_MS = 2000

# Where one pass of a looped song hands over to the next. Not a plain repeat:
# a song ends on its own fade-out (and downloads add silence on top), so
# repeated end to end the music dropped out for 1.5-10s every pass and then
# restarted on its intro - measured on all ten tracks in global/bgm, every
# three minutes or so of a chapter. The dead air is trimmed off both ends,
# and each pass's end overlaps the next one's start for this long.
BGM_LOOP_CROSSFADE_MS = 4000
# What counts as dead air at a song's ends: this far under its typical level.
BGM_SILENCE_UNDER_DB = 30.0
# With a pause between passes (audio.bgm_loop_gap_s), each pass instead ends
# on its own: faded out over this long (most songs already fade, this catches
# the ones that stop dead), then the pause, then the song again from its
# intro, which only gets a click-proof start - it is meant to be heard
# beginning again, as a playlist would.
BGM_LOOP_FADE_OUT_MS = 1500
BGM_LOOP_RESTART_FADE_MS = 50
# Bumped whenever music_bed changes what it makes, so a mix built the old way
# is not mistaken for up to date (audio/mix.py's fingerprint carries it).
BED_VERSION = 3

# The master's true-peak ceiling, and how far under it the peak guard holds
# samples (it limits samples; true peak between them reads a little higher).
LOUDNORM_TRUE_PEAK = -1.0
LIMITER_MARGIN_DB = 1.0

# A take's two ends are faded over this long, so a take never starts or
# stops on a click. The start only ever fades across the silence already
# there (audio/clips.py:apply_edge_fades), so no word is ramped.
EDGE_FADE_MS = 35


def panel_segments(audio_dir: Path, panel: dict[str, Any], sample_rate: int,
                   edge_fade_ms: int = EDGE_FADE_MS) -> list[AudioSegment]:
    """One panel's place in the narration track: its synthesized clip - or
    silence of the same length, for a panel whose clip is missing, so the
    track stays true to audio_timing.json either way - plus the pause held
    after it."""
    clip_file = audio_dir / panel["audio_file"]
    if clip_file.exists():
        # Exactly the slice audio_timing.json names - the clip's speech, with
        # the silence the synthesizer baked around it trimmed back to an even
        # margin. Taking the whole file instead would put an unchosen and
        # uneven pause before every panel, and would make the master longer
        # than the timeline the video is cut to.
        clip = AudioSegment.from_file(clip_file)
        start_ms = panel.get("clip_start_ms", 0)
        clip = clip[start_ms:start_ms + panel["duration_ms"]]
        # Faded here rather than baked into the clip on disk: the fade is how
        # the chapter is put together, not part of what was synthesized, so
        # changing it costs a re-mix instead of narrating everything again.
        #
        # A panel in the middle of a batched take asks for neither edge - its
        # neighbours are the same generation, already adjacent samples. Rows
        # written before batching existed carry neither key and get both,
        # which is what they have always had.
        segments = [apply_edge_fades(clip, edge_fade_ms,
                                     fade_in=panel.get("fade_in", True),
                                     fade_out=panel.get("fade_out", True))]
    else:
        segments = [AudioSegment.silent(duration=panel["duration_ms"], frame_rate=sample_rate)]

    pause_ms = panel.get("pause_after_ms", 0)
    if pause_ms > 0:
        segments.append(AudioSegment.silent(duration=pause_ms, frame_rate=sample_rate))
    return segments


def load_bgm(path: str | Path, sample_rate: int) -> AudioSegment:
    """The music file as stereo at the project's own rate.

    Through resample.load_audio for the same reason the narration clips are
    (see audio/resample.py): a bed is rarely already at the project rate -
    the bundled track is 48 kHz against a 44.1 kHz project - and pydub's own
    resampler would fold imaging noise across the whole music bed on the way
    down."""
    return load_audio(Path(path), sample_rate, channels=2)


def measure_loudness(path: Path) -> tuple[float | None, float | None]:
    """A file's integrated loudness in LUFS and true peak in dBTP (EBU R128,
    ffmpeg's ebur128), each None when it can't be measured (silence, an
    unreadable file). ~1 s for a 7-minute chapter."""
    result = run_ffmpeg(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                         "-f", "null", "-"], capture=True)
    err = result.stderr or ""
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    peak = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", err)
    loudness = float(found[-1]) if found else None
    true_peak = float(peak[-1]) if peak and peak[-1] != "-inf" else None
    return (loudness if loudness is not None and loudness > -70 else None), true_peak


def loud_parts_loudness(path: Path) -> float | None:
    """How loud a file's loud parts are, in LUFS: EBU R128's "LRA high", the
    95th percentile of its 3-second loudness - a chorus or a drop, not the
    average. ~1 s for a 7-minute chapter. None when it can't be measured."""
    result = run_ffmpeg(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128",
                         "-f", "null", "-"], capture=True)
    found = re.findall(r"LRA high:\s+(-?[\d.]+) LUFS", result.stderr or "")
    value = float(found[-1]) if found else None
    return value if value is not None and value > -70 else None


def integrated_loudness(path: Path) -> float | None:
    """A file's integrated loudness in LUFS, or None (see measure_loudness)."""
    return measure_loudness(path)[0]


def _samples(seg: AudioSegment) -> np.ndarray:
    """A segment as float frames, shape (frames, channels)."""
    full = 1 << (8 * seg.sample_width - 1)
    return np.array(seg.get_array_of_samples(), dtype=np.float64).reshape(-1, seg.channels) / full


def _segment(frames: np.ndarray, like: AudioSegment) -> AudioSegment:
    full = 1 << (8 * like.sample_width - 1)
    ints = np.clip(np.round(frames * full), -full, full - 1).astype({2: np.int16, 4: np.int32}[like.sample_width])
    return like._spawn(ints.reshape(-1).tobytes())


def trim_dead_air(frames: np.ndarray, sample_rate: int) -> np.ndarray:
    """The song without the silence (or near silence) at either end - anything
    BGM_SILENCE_UNDER_DB under its typical level, in 50 ms steps. A quiet
    intro or outro that is still music stays: it is well above that."""
    step = max(1, sample_rate // 20)
    usable = len(frames) // step * step
    if not usable:
        return frames
    rms = np.sqrt(np.mean(frames[:usable].reshape(-1, step, frames.shape[1]) ** 2, axis=(1, 2)))
    floor = np.median(rms) * 10 ** (-BGM_SILENCE_UNDER_DB / 20)
    loud = np.flatnonzero(rms > floor)
    if not len(loud):
        return frames
    return frames[loud[0] * step:(loud[-1] + 1) * step]


def music_bed(narration: AudioSegment, bgm: AudioSegment, gap_ms: int = 0) -> AudioSegment:
    """The music looped to the narration's length, faded in and out once - the
    exact stretch the mix plays, so it is also what gets measured.

    Each pass is the song with its dead air trimmed (trim_dead_air). With no
    gap, each pass's end crossfades into the next one's start over
    BGM_LOOP_CROSSFADE_MS with equal-power curves: the two halves sum to
    steady loudness through the overlap, where a linear crossfade sags in the
    middle, so the music never stops. With `gap_ms`, each pass fades out
    (BGM_LOOP_FADE_OUT_MS), the music rests for `gap_ms`, and the song starts
    over - a breath between plays rather than a seam (user request,
    2026-10-26: "a small delay between the loop to make it feel natural")."""
    need = int(len(narration) * bgm.frame_rate / 1000)
    parts = loop_parts(bgm, gap_ms)
    if parts is None:
        return AudioSegment.silent(duration=len(narration), frame_rate=bgm.frame_rate).set_channels(bgm.channels)
    head, unit = parts
    repeats = max(0, -(-(need - len(head)) // len(unit)))
    bed = np.concatenate([head, np.tile(unit, (repeats, 1))])[:need]
    return _segment(bed, bgm).fade_in(BGM_FADE_IN_MS).fade_out(BGM_FADE_OUT_MS)


def loop_parts(bgm: AudioSegment, gap_ms: int) -> tuple[np.ndarray, np.ndarray] | None:
    """The looped song as its first play and the part that then repeats for
    ever: head + unit + unit + ... is the bed (music_bed), cut to length.
    With a gap both are one play and its pause; with a crossfade the unit is
    the crossfade and the song after it. None for a song that is all silence."""
    song = trim_dead_air(_samples(bgm), bgm.frame_rate)
    if not len(song):
        return None
    rate = bgm.frame_rate
    if gap_ms > 0:
        one = song.copy()
        tail = min(int(BGM_LOOP_FADE_OUT_MS * rate / 1000), len(one) // 4)
        if tail > 0:
            one[-tail:] *= np.cos(np.linspace(0.0, np.pi / 2, tail))[:, None]
        head = min(int(BGM_LOOP_RESTART_FADE_MS * rate / 1000), len(one) // 4)
        if head > 0:
            one[:head] *= np.sin(np.linspace(0.0, np.pi / 2, head))[:, None]
        play = np.concatenate([one, np.zeros((int(gap_ms * rate / 1000), one.shape[1]))])
        return play, play
    overlap = min(int(BGM_LOOP_CROSSFADE_MS * rate / 1000), len(song) // 4)
    if overlap <= 0:
        return song, song
    t = np.linspace(0.0, np.pi / 2, overlap)[:, None]
    joined = song[-overlap:] * np.cos(t) + song[:overlap] * np.sin(t)
    return song[:-overlap], np.concatenate([joined, song[overlap:-overlap]])


def write_music_bed(seconds: float, bgm: AudioSegment, gap_ms: int, out: Path) -> bool:
    """music_bed for `seconds` of narration, written to `out` - streamed by
    ffmpeg from one play and the repeating part, so a long video of many
    chapters never holds hours of music in memory. False for a silent song."""
    parts = loop_parts(bgm, gap_ms)
    if parts is None:
        return False
    head_wav, unit_wav = out.with_name(out.stem + "_head.wav"), out.with_name(out.stem + "_unit.wav")
    try:
        for frames, path in zip(parts, (head_wav, unit_wav), strict=True):
            _segment(frames, bgm).export(path, format="wav")
        fade_out_at = max(seconds - BGM_FADE_OUT_MS / 1000, 0.0)
        chain = (f"[0:a][1:a]concat=n=2:v=0:a=1,atrim=duration={seconds:.6f},"
                 f"afade=t=in:d={BGM_FADE_IN_MS / 1000:g},"
                 f"afade=t=out:st={fade_out_at:.6f}:d={BGM_FADE_OUT_MS / 1000:g}")
        run_ffmpeg(["ffmpeg", "-y", "-i", str(head_wav), "-stream_loop", "-1", "-i", str(unit_wav),
                    "-filter_complex", chain, "-t", f"{seconds:.6f}", "-c:a", "pcm_f32le", str(out)],
                   check=True, capture=True)
    finally:
        head_wav.unlink(missing_ok=True)
        unit_wav.unlink(missing_ok=True)
    return True


def under_narration(narration: AudioSegment, bed: AudioSegment, volume_db: float) -> AudioSegment:
    """The narration over a music bed (music_bed) set to `volume_db`."""
    return (bed + volume_db).overlay(narration)


# How far under its target a guarded master may land before the gain is
# raised by the shortfall and the guard run again.
LOUDNESS_TOLERANCE_LU = 0.3
GUARD_PASSES = 3


def _apply_gain(raw_path: Path, final_path: Path, sample_rate: int, gain_db: float, guarded: bool) -> None:
    """`raw_path` turned up by `gain_db` into `final_path`, with the peak guard
    when `guarded`: a little under the ceiling, since it limits samples and
    the ceiling is in true peak; nothing under it is touched."""
    chain = [f"volume={gain_db:.2f}dB"]
    if guarded:
        ceiling = 10 ** ((LOUDNORM_TRUE_PEAK - LIMITER_MARGIN_DB) / 20)
        chain.append(f"alimiter=limit={ceiling:.4f}:level=disabled:attack=5:release=50")
    run_ffmpeg(["ffmpeg", "-y", "-i", str(raw_path), "-af", ",".join(chain), "-ar", str(sample_rate),
                str(final_path)], check=True, capture=True)


def write_master(raw_path: Path, final_path: Path, sample_rate: int, *, target_lufs: float,
                 announcement: str = "", on_failure: str = "the track as it was") -> None:
    """Puts the raw master in place as the finished one, at `target_lufs`.

    Measure, then one linear gain for the whole track - the level changes,
    nothing else does (a gain that rode up and down pumped the music between
    sentences). Measured with ebur128 and applied with `volume`: ~2 s for a
    7-minute chapter. Only when that gain would push a peak over the ceiling
    is a peak guard added, holding just those peaks (and what loudness it
    took is given back); otherwise the track is the voice and music exactly
    as mixed, louder or quieter. A failed pass is
    a warning: the track as it was is used instead, because a recap at the
    wrong volume beats no recap at all."""
    console.print(f"[cyan]{announcement}[/]")
    try:
        loudness, peak = measure_loudness(raw_path)
        if loudness is None:
            raise ValueError("the track is silent or unreadable")
        gain = target_lufs - loudness
        guarded = peak is not None and peak + gain > LOUDNORM_TRUE_PEAK
        _apply_gain(raw_path, final_path, sample_rate, gain, guarded)
        # The guard takes loudness off with the peaks it holds - a peaky voice
        # measured a whole LU short (Drama 3: -15.0 for -14, then -14.4 after
        # one pass) - so what it took is measured and given back, through it
        # again, until it is close.
        for _ in range(GUARD_PASSES if guarded else 0):
            reached, _ = measure_loudness(final_path)
            if reached is None or target_lufs - reached <= LOUDNESS_TOLERANCE_LU:
                break
            gain += target_lufs - reached
            _apply_gain(raw_path, final_path, sample_rate, gain, True)
        raw_path.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[yellow]Setting the volume failed ({_esc(str(e))}) - using {on_failure}.[/]")
        raw_path.replace(final_path)
