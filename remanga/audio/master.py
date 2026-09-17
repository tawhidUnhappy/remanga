"""Building a chapter's master audio track: the narration clips end to end,
the music bed under them, and the loudness pass over the result."""

from __future__ import annotations

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

# What a finished master is normalized to: -16 LUFS, what streaming
# platforms expect (EBU R128).
LOUDNORM_FILTER = "loudnorm=I=-16:LRA=11:TP=-1.5"


def page_segments(audio_dir: Path, page: dict[str, Any], sample_rate: int) -> list[AudioSegment]:
    """One page's place in the narration track: its synthesized clip - or
    silence of the same length, for a page whose clip is missing, so the
    track stays true to audio_timing.json either way - plus the pause held
    after it."""
    clip_file = audio_dir / page["audio_file"]
    if clip_file.exists():
        segments = [AudioSegment.from_file(clip_file)]
    else:
        segments = [AudioSegment.silent(duration=page["duration_ms"], frame_rate=sample_rate)]

    pause_ms = page.get("pause_after_ms", 0)
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


def under_narration(narration: AudioSegment, bgm: AudioSegment, volume_db: float) -> AudioSegment:
    """The narration over the music: the bed set to `volume_db`, looped to
    the narration's length, and faded in and out exactly once - so however
    many chapters this covers, the music arrives and leaves once, and never
    restarts at a join."""
    bed = bgm + volume_db
    total_duration_ms = len(narration)
    loop_count = (total_duration_ms // max(1, len(bed))) + 1
    bed = (bed * loop_count)[:total_duration_ms]
    bed = bed.fade_in(BGM_FADE_IN_MS).fade_out(BGM_FADE_OUT_MS)
    return bed.overlay(narration)


def write_master(raw_path: Path, final_path: Path, sample_rate: int, *, normalize: bool,
                 announcement: str = "", on_failure: str = "the un-normalized track",
                 progress: tuple[str, float] | None = None) -> None:
    """Puts the raw master in place as the finished one, normalized when
    asked for.

    A failed loudnorm pass is a warning rather than an error: the
    un-normalized master is moved into place instead, because a recap at the
    wrong loudness beats no recap at all."""
    if not normalize:
        raw_path.rename(final_path)
        return

    console.print(f"[cyan]{announcement}[/]")
    cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-af", LOUDNORM_FILTER, "-ar", str(sample_rate), str(final_path)]
    try:
        if progress is not None:
            run_ffmpeg(cmd, check=True, capture=True, show_progress=True,
                       total_seconds=progress[1], description=progress[0])
        else:
            run_ffmpeg(cmd, check=True, capture=True)
        raw_path.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[yellow]Loudnorm filter warning: {_esc(str(e))}. Falling back to {on_failure}.[/]")
        raw_path.rename(final_path)
