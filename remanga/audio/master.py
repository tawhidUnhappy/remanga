"""Building a chapter's master audio track: the narration clips end to end,
the music bed under them, and the loudness pass over the result."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga.audio.resample import load_audio
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg

# Long enough to hear the music arrive and leave rather than cut, short
# enough not to swallow the first line of narration.
BGM_FADE_IN_MS = 1500
BGM_FADE_OUT_MS = 2000

# Loudness range and true-peak ceiling for the normalized master.
LOUDNORM_LRA = 11
LOUDNORM_TRUE_PEAK = -1.0


def panel_segments(audio_dir: Path, panel: dict[str, Any], sample_rate: int) -> list[AudioSegment]:
    """One panel's place in the narration track: its synthesized clip - or
    silence of the same length, for a panel whose clip is missing, so the
    track stays true to audio_timing.json either way - plus the pause held
    after it."""
    clip_file = audio_dir / panel["audio_file"]
    if clip_file.exists():
        segments = [AudioSegment.from_file(clip_file)]
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


def integrated_loudness(path: Path) -> float | None:
    """A file's integrated loudness in LUFS (EBU R128), or None when it can't
    be measured (silence, an unreadable file)."""
    result = run_ffmpeg(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                        capture=True)
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", result.stderr or "")
    value = float(found[-1]) if found else None
    return value if value is not None and value > -70 else None


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

    Two passes: the first measures, the second applies one linear gain from
    those measurements - single-pass loudnorm rides the gain up and down
    through the track, which pumps the music between sentences. A failed pass
    is a warning: the un-normalized master is used instead, because a recap at
    the wrong loudness beats no recap at all."""
    if not normalize:
        raw_path.replace(final_path)
        return

    console.print(f"[cyan]{announcement}[/]")
    base = f"loudnorm=I={target_lufs:g}:LRA={LOUDNORM_LRA}:TP={LOUDNORM_TRUE_PEAK:g}"
    try:
        measured = run_ffmpeg(["ffmpeg", "-hide_banner", "-nostats", "-i", str(raw_path), "-af",
                               f"{base}:print_format=json", "-f", "null", "-"], check=True, capture=True)
        # loudnorm prints its measurements as the last {...} block on stderr,
        # with ffmpeg's own summary lines after it.
        err = measured.stderr or ""
        stats = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
        second = (f"{base}:measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}"
                  f":measured_TP={stats['input_tp']}:measured_thresh={stats['input_thresh']}"
                  f":offset={stats['target_offset']}:linear=true")
        run_ffmpeg(["ffmpeg", "-y", "-i", str(raw_path), "-af", second, "-ar", str(sample_rate), str(final_path)],
                   check=True, capture=True)
        raw_path.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[yellow]Loudness normalization failed ({_esc(str(e))}) - using {on_failure}.[/]")
        raw_path.replace(final_path)
