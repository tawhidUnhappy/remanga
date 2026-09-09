"""Works out what the music gain SHOULD be, by measuring what you have.

`bgm_volume_db` is relative to the music file's own loudness, which makes it
a number nobody can set correctly by intuition: the same value under two
tracks mastered a few dB apart puts the music a few dB apart under the
narration. The usual result is a value carried over from a previous track
that is quietly wrong for the current one.

So rather than have the mix silently compute a level on every run - which
hides the number and makes the config unreadable - this measures both sides
once, on request, and hands back a figure to WRITE into config.json. The
value stays a plain number somebody can look at, question and nudge, which is
the property a settings file should have.

Broadcast practice puts music 15-20dB below dialogue. Under 15 it starts
masking consonants, and that is worst on phone speakers, which is where most
of this gets watched."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment

from remanga.audio.resample import load_audio
from remanga.paths import get_projects_dir

# Measured for Kokoro-82M narration, speech-only, across a real chapter.
# Used when a project has not synthesized anything yet, so the action still
# gives a usable answer on a fresh install instead of refusing to help.
TYPICAL_NARRATION_DBFS = -26.3

# Enough speech to be representative without reading a whole chapter off disk.
_MAX_CLIPS = 40


@dataclass(frozen=True)
class LevelReading:
    narration_dbfs: float
    bgm_dbfs: float
    suggested_gain_db: float
    clips_measured: int          # 0 means the typical figure was used
    current_separation_db: float


def _speech_dbfs_from_clips(clips: list[Path]) -> tuple[float | None, int]:
    """Speech-only loudness across `clips`, as summed squared RMS weighted by
    frame count - the same figure the mix would see, without the inter-panel
    silence that drags a finished track's RMS below what narration sounds
    like."""
    total_sq = 0.0
    total_frames = 0
    peak_amp = 0
    for clip in clips:
        try:
            seg = AudioSegment.from_file(clip)
        except Exception:
            continue
        frames = int(seg.frame_count())
        if frames <= 0 or seg.rms <= 0:
            continue
        total_sq += float(seg.rms) ** 2 * frames
        total_frames += frames
        peak_amp = max(peak_amp, seg.max_possible_amplitude)
    if total_frames <= 0 or peak_amp <= 0:
        return None, 0
    rms = math.sqrt(total_sq / total_frames)
    return 20 * math.log10(rms / peak_amp), len(clips)


def find_narration_clips(limit: int = _MAX_CLIPS) -> list[Path]:
    """Synthesized narration already on disk, from any project.

    Any project, deliberately: the question being answered is "how loud does
    this engine's narration come out", which is a property of the voice and
    the engine rather than of one manga."""
    projects = get_projects_dir()
    if not projects.is_dir():
        return []
    clips: list[Path] = []
    for audio_dir in sorted(projects.glob("*/audio/chapter_*")):
        for clip in sorted(audio_dir.glob("*.wav")):
            clips.append(clip)
            if len(clips) >= limit:
                return clips
    return clips


def read_levels(bgm_path: str | Path, sample_rate: int, target_below_db: float,
                current_gain_db: float) -> LevelReading | None:
    """Measure narration and music, and suggest the gain that separates them
    by `target_below_db`. None when the music file cannot be read."""
    bgm_file = Path(str(bgm_path or "")).expanduser()
    if not bgm_file.is_file():
        return None
    try:
        bgm = load_audio(bgm_file, sample_rate, channels=2)
    except Exception:
        return None
    if bgm.rms <= 0:
        return None

    measured, count = _speech_dbfs_from_clips(find_narration_clips())
    narration = TYPICAL_NARRATION_DBFS if measured is None else measured

    return LevelReading(
        narration_dbfs=narration,
        bgm_dbfs=bgm.dBFS,
        suggested_gain_db=round(narration - target_below_db - bgm.dBFS, 1),
        clips_measured=0 if measured is None else count,
        current_separation_db=narration - (bgm.dBFS + current_gain_db),
    )
