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

Both sides are measured as ITU-R BS.1770 integrated loudness (LUFS) rather
than as plain RMS, via ffmpeg's `ebur128`. That is not pedantry: the two
disagree by an amount that depends on the material. Measured on this repo's
bed, RMS reads -12.61 dBFS where loudness reads -9.90 LUFS - 2.7 units
louder - because BS.1770 K-weights (roughly, how an ear weights frequency)
and gates out near-silence, and music is spectrally dense where speech is
not. Narration, by contrast, reads almost identically either way. So an
RMS-derived gain systematically leaves the music louder than intended, and
by a margin that changes with the track.

It is also the measure the rest of the pipeline already speaks: the master
is normalized with EBU R128 (audio/mix.py), so setting the balance in the
same units means the number here survives that pass unchanged.

Broadcast practice puts music 15-20 LU below dialogue. Under 15 it starts
masking consonants, and that is worst on phone speakers, which is where most
of this gets watched. A recap is spoken word from end to end - there is no
scene the music carries on its own - so the default sits just past the quiet
end of that band; see BALANCE_PRESETS for the named choices around it."""

from __future__ import annotations

import re
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

from remanga.audio.clips import clamp_boost
from remanga.json_io import read_json_or
from remanga.paths import get_projects_dir

# Integrated loudness of Kokoro-82M narration at volume_boost_db 0, measured
# across a real chapter. Used when a project has not synthesized anything
# yet, so the action still answers on a fresh install instead of refusing to
# help.
TYPICAL_NARRATION_LUFS = -25.7

# A few clips, not one and not all. The engine reads at a consistent level -
# same voice, same settings - and measuring six real clips put them within
# 0.34 LU of each other, so a handful is already at the noise floor of the
# question. The median of them shrugs off a clip that happens to be a single
# quiet word, which one clip on its own cannot do.
_MAX_CLIPS = 5

# bgm_volume_db's own range, so a reading can never suggest a value the
# settings screen would refuse to write. Nothing realistic reaches either
# end: at this narration level the lower one needs a music file louder than
# full scale and the upper one needs a file quieter than -65 LUFS.
_MIN_GAIN_DB, _MAX_GAIN_DB = -60.0, 20.0


@dataclass(frozen=True)
class BalancePreset:
    """One named answer to "how loud should the music be", as a separation
    in LU below the narration.

    Named rather than left as a bare number because the number is the part
    nobody has intuition for: "20" means nothing, "the bed is felt rather
    than heard" is the thing somebody actually wants. Every value here is
    inside the 15-20 LU band broadcast uses for music under dialogue, or
    deliberately past its quiet end - a recap is spoken word from start to
    finish, and the voice IS the content."""

    key: str
    label: str
    separation_db: float
    note: str


BALANCE_PRESETS: tuple[BalancePreset, ...] = (
    BalancePreset(
        "recap", "Voice first", 20.0,
        "how most manga recaps sit - the bed is felt rather than heard",
    ),
    BalancePreset(
        "quiet", "Almost silent bed", 24.0,
        "music only just present; the safest choice on phone speakers",
    ),
    BalancePreset(
        "present", "Music noticeable", 17.0,
        "the bed comes up between lines, still clearly under the voice",
    ),
    BalancePreset(
        "forward", "Music forward", 14.0,
        "about as loud as music gets before it starts masking consonants",
    ),
)

# What a fresh install balances to, and what the first row of the picker
# offers. Also the default of audio.bgm_target_below_narration_db - the two
# are the same decision, so they are the same number.
DEFAULT_SEPARATION_DB = BALANCE_PRESETS[0].separation_db

PRESET_BY_SEPARATION = {preset.separation_db: preset for preset in BALANCE_PRESETS}


@dataclass(frozen=True)
class NarrationSample:
    """Narration clips to measure, and the gain already baked into them."""

    clips: list[Path]
    baked_boost_db: float


@dataclass(frozen=True)
class LevelReading:
    narration_lufs: float
    bgm_lufs: float
    suggested_gain_db: float
    clips_measured: int          # 0 means the typical figure was used
    current_separation_db: float


def _integrated_lufs(path: Path) -> float | None:
    """ITU-R BS.1770 integrated loudness for a file, or None if unmeasurable.

    ffmpeg's `ebur128` in one streaming pass. `loudnorm`'s two-pass JSON
    reports the same figure - measured, 0.07 LU apart on this repo's bed -
    and took 3409ms against 122ms, so there is nothing to be bought by the
    slower one. Neither holds the audio in memory."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "ebur128=framelog=quiet", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    # The summary block at the end, not the per-frame log: the last "I:" line
    # is the integrated figure over the whole file.
    matches = re.findall(r"I:\s*(-?[\d.]+)\s*LUFS", result.stderr)
    if not matches:
        return None
    value = float(matches[-1])
    # A file of pure silence reports -inf; treat that as unmeasurable rather
    # than propagating an infinity into a gain calculation.
    return None if value < -70 else value


def _narration_lufs(clips: list[Path]) -> tuple[float | None, int]:
    """Median integrated loudness across `clips`.

    Median, not mean: one clip that is a single quiet word would drag an
    average, and narration clips are one line each so that is a real case."""
    values = [v for v in (_integrated_lufs(c) for c in clips) if v is not None]
    if not values:
        return None, 0
    return statistics.median(values), len(values)


def find_narration_clips(limit: int = _MAX_CLIPS) -> NarrationSample:
    """Synthesized narration already on disk, from any project.

    Any project, deliberately: the question being answered is "how loud does
    this engine's narration come out", which is a property of the voice and
    the engine rather than of one manga.

    One chapter's folder rather than a handful swept across several, because
    the sample has to come with the gain that was baked into it: clips carry
    their volume_boost_db from the run that wrote them (audio/tts.py), and
    the chapter's audio_timing.json next to them is what records it. Clips
    from two chapters synthesized at different boosts have no single answer
    to that, and averaging across them would quietly measure neither."""
    projects = get_projects_dir()
    if not projects.is_dir():
        return NarrationSample([], 0.0)
    for audio_dir in sorted(projects.glob("*/audio/chapter_*")):
        clips = sorted(audio_dir.glob("*.wav"))[:limit]
        if not clips:
            continue
        baked = read_json_or(audio_dir / "audio_timing.json", {}).get("volume_boost_db", 0.0)
        return NarrationSample(clips, clamp_boost(baked))
    return NarrationSample([], 0.0)


def read_levels(bgm_path: str | Path, target_below_db: float, current_gain_db: float,
                narration_boost_db: float = 0.0) -> LevelReading | None:
    """Measure narration and music, and suggest the gain that separates them
    by `target_below_db`. None when the music file cannot be read.

    `narration_boost_db` is the voice gain currently configured
    (tts.<engine>.volume_boost_db). It matters because the two sides of this
    calculation are measured at different times: the music file is measured
    as it is now, but the narration is measured from clips written by an
    earlier run, at whatever boost was configured THEN. The next tts run
    applies the difference to those clips, so the level that will actually
    be mixed is the measured one plus that difference - which is what gets
    balanced against, rather than the level currently on disk."""
    bgm_file = Path(str(bgm_path or "")).expanduser()
    if not bgm_file.is_file():
        return None
    bgm_lufs = _integrated_lufs(bgm_file)
    if bgm_lufs is None:
        return None

    boost = clamp_boost(narration_boost_db)
    sample = find_narration_clips()
    measured, count = _narration_lufs(sample.clips)
    narration = (
        TYPICAL_NARRATION_LUFS + boost if measured is None
        else measured + (boost - sample.baked_boost_db)
    )

    suggested = round(narration - target_below_db - bgm_lufs, 1)
    return LevelReading(
        narration_lufs=narration,
        bgm_lufs=bgm_lufs,
        suggested_gain_db=max(_MIN_GAIN_DB, min(_MAX_GAIN_DB, suggested)),
        clips_measured=0 if measured is None else count,
        current_separation_db=narration - (bgm_lufs + current_gain_db),
    )
