"""Building a chapter's master audio track: the narration clips end to end,
the music bed under them, and the loudness pass over the result."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga.audio.clips import apply_edge_fades
from remanga.audio.resample import load_audio
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg

# Long enough to hear the music arrive and leave rather than cut, short
# enough not to swallow the first line of narration.
BGM_FADE_IN_MS = 1500
BGM_FADE_OUT_MS = 2000

# The normalized master's true-peak ceiling, and how far under it the peak
# limiter holds samples (it limits samples; true peak between them reads a
# little higher).
LOUDNORM_TRUE_PEAK = -1.0
LIMITER_MARGIN_DB = 0.5


def panel_segments(audio_dir: Path, panel: dict[str, Any], sample_rate: int,
                   edge_fade_ms: int = 0) -> list[AudioSegment]:
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


def integrated_loudness(path: Path) -> float | None:
    """A file's integrated loudness in LUFS, or None (see measure_loudness)."""
    return measure_loudness(path)[0]


def music_bed(narration: AudioSegment, bgm: AudioSegment) -> AudioSegment:
    """The music looped to the narration's length, faded in and out once - the
    exact stretch the mix plays, so it is also what gets measured."""
    loop_count = (len(narration) // max(1, len(bgm))) + 1
    return (bgm * loop_count)[:len(narration)].fade_in(BGM_FADE_IN_MS).fade_out(BGM_FADE_OUT_MS)


def under_narration(narration: AudioSegment, bed: AudioSegment, volume_db: float) -> AudioSegment:
    """The narration over a music bed (music_bed) set to `volume_db`."""
    return (bed + volume_db).overlay(narration)


def write_master(raw_path: Path, final_path: Path, sample_rate: int, *, normalize: bool, target_lufs: float,
                 announcement: str = "", on_failure: str = "the un-normalized track") -> None:
    """Puts the raw master in place as the finished one, normalized to
    `target_lufs` when asked for.

    Measure, then one linear gain - never a gain that rides up and down
    through the track (single-pass loudnorm did, and pumped the music between
    sentences). Measured with ebur128 and applied with `volume` rather than
    two loudnorm passes: loudnorm upsamples to 192 kHz to do the same job, and
    took 22 of a 7-minute chapter's 24 s of mixing; this takes ~2 s. Peaks the
    gain would push over the ceiling are held by a limiter, not the track
    turned down. A failed pass
    is a warning: the un-normalized master is used instead, because a recap at
    the wrong loudness beats no recap at all."""
    if not normalize:
        raw_path.replace(final_path)
        return

    console.print(f"[cyan]{announcement}[/]")
    try:
        loudness, peak = measure_loudness(raw_path)
        if loudness is None:
            raise ValueError("the track is silent or unreadable")
        gain = target_lufs - loudness
        chain = [f"volume={gain:.2f}dB"]
        if peak is not None and peak + gain > LOUDNORM_TRUE_PEAK:
            # The gain would push a few peaks over the ceiling: hold just those
            # (a peak limiter a little under it, since it limits samples and
            # the ceiling is in true peak) rather than lowering the whole track.
            ceiling = 10 ** ((LOUDNORM_TRUE_PEAK - LIMITER_MARGIN_DB) / 20)
            chain.append(f"alimiter=limit={ceiling:.4f}:level=disabled:attack=5:release=50")
        run_ffmpeg(["ffmpeg", "-y", "-i", str(raw_path), "-af", ",".join(chain), "-ar", str(sample_rate),
                    str(final_path)], check=True, capture=True)
        raw_path.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[yellow]Loudness normalization failed ({_esc(str(e))}) - using {on_failure}.[/]")
        raw_path.replace(final_path)
