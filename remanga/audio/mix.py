"""A chapter's master track: the narration as the engine read it, background
music under it, brought to the volume asked for.

Skipped when master_audio.wav already matches: the synthesized audio
(audio_timing.json, rewritten only when its content changes) and every mix
setting are fingerprinted, so a plain re-run doesn't re-mix - and in turn
doesn't make the render think the sound changed."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga.audio.join import join_segments
from remanga.audio.manifest import verify_audio_manifest
from remanga.audio.master import (
    BED_VERSION,
    integrated_loudness,
    load_bgm,
    loud_parts_loudness,
    music_bed,
    panel_segments,
    under_narration,
    write_master,
    write_music_bed,
)
from remanga.config import AudioConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json, read_json_or, write_json
from remanga.paths import get_audio_dir, get_audio_timing_path, get_master_audio_path


def _bgm_file(config: AudioConfig) -> Path | None:
    if not config.bgm_enabled:
        return None
    path = Path(str(config.bgm_path or "")).expanduser()
    if path.is_file():
        return path
    console.print(f"[yellow]Background music is on, but '{_esc(str(config.bgm_path))}' isn't a file - mixing "
                  f"without music.[/]")
    return None


# The gain used when a loudness can't be measured: a typical modern track
# (about -10 LUFS) against Kokoro's narration (about -26 LUFS).
FALLBACK_MUSIC_GAIN_DB = -30.0


# How the music is measured against the voice; bumped when that changes, so
# a mix made the old way is mixed again (it is in the fingerprint).
MUSIC_MEASURE = "loud-parts-v1"


def music_gain_db(narration_wav: Path, bed_wav: Path, below_voice_lu: float) -> float:
    """The gain that puts the music bed's LOUD PARTS `below_voice_lu` under
    the narration: the voice by its integrated loudness, the music by its
    loud parts (master.loud_parts_loudness, the 95th percentile of its
    3-second loudness) - both over exactly what the mix plays. By its average
    instead, a song with quiet verses and a loud chorus came in quiet on
    average and loud at the chorus: over the twelve tracks in global/bgm the
    loud parts sit 0.6-3.0 LU over the average, so one setting meant up to
    3 LU more music at the peaks of one song than of another (user request,
    2026-10-25: a level that works "for almost all background music even
    the loud and uncommon ones")."""
    voice, music = integrated_loudness(narration_wav), loud_parts_loudness(bed_wav)
    if voice is None or music is None:
        return FALLBACK_MUSIC_GAIN_DB
    return round(voice - below_voice_lu - music, 1)


def _fingerprint(timing_path: Path, config: AudioConfig, bgm: Path | None) -> dict[str, Any]:
    bgm_stat = bgm.stat() if bgm else None
    return {
        "timing_mtime": timing_path.stat().st_mtime,
        "bgm": [str(bgm), bgm_stat.st_size, int(bgm_stat.st_mtime)] if bgm_stat else None,
        "bgm_below_voice_lu": config.bgm_below_voice_lu,
        "bgm_loop_gap_s": config.bgm_loop_gap_s if bgm else None,
        "music_measure": MUSIC_MEASURE if bgm else None,
        "bed_version": BED_VERSION if bgm else None,
        "sample_rate": config.sample_rate,
        "volume_lufs": config.volume_lufs,
    }


def narration_track(project_name: str, chapter_num: str, config: AudioConfig) -> AudioSegment:
    """A chapter's narration as the engine read it, every take end to end
    with its pauses - no music, no volume set yet."""
    timing_path = get_audio_timing_path(project_name, chapter_num)
    if not timing_path.exists():
        raise FileNotFoundError(f"No narration audio for chapter {chapter_num} yet: {timing_path}")
    audio_dir = get_audio_dir(project_name, chapter_num)
    # Zero trust on the folder before reading a single clip out of it - the
    # mix is exactly the point where "some of the raw audio" would otherwise
    # quietly become "a chapter missing a few lines" with nothing to say so.
    verify_audio_manifest(audio_dir, chapter_num)
    segments = []
    for panel in read_json(timing_path).get("panels", []):
        segments.extend(panel_segments(audio_dir, panel, config.sample_rate))
    return join_segments(segments).set_channels(2).set_frame_rate(config.sample_rate)


def mix_master_audio(project_name: str, chapter_num: str, config: AudioConfig, force: bool = False) -> Path:
    timing_path = get_audio_timing_path(project_name, chapter_num)
    if not timing_path.exists():
        raise FileNotFoundError(f"No narration audio for chapter {chapter_num} yet: {timing_path}")
    master = get_master_audio_path(project_name, chapter_num)
    fingerprint_path = master.with_name("master_audio_fingerprint.json")
    bgm = _bgm_file(config)

    fingerprint = _fingerprint(timing_path, config, bgm)
    if (not force and master.exists() and master.stat().st_size > 1000
            and read_json_or(fingerprint_path, None) == fingerprint):
        console.print(f"[dim]✓ Chapter {chapter_num}'s audio mix is already up to date.[/]")
        return master

    console.print(f"[cyan]Mixing chapter {chapter_num}'s audio...[/]")
    track = narration_track(project_name, chapter_num, config)

    raw = master.with_name("master_audio_raw.wav")
    if bgm:
        bed = music_bed(track, load_bgm(bgm, config.sample_rate), gap_ms=round(config.bgm_loop_gap_s * 1000))
        bed_wav = master.with_name("music_bed.wav")
        track.export(raw, format="wav")
        bed.export(bed_wav, format="wav")
        gain_db = music_gain_db(raw, bed_wav, config.bgm_below_voice_lu)
        bed_wav.unlink(missing_ok=True)
        console.print(f"[cyan]Adding background music:[/] {_esc(str(bgm))} "
                      f"[dim](its loud parts {config.bgm_below_voice_lu:g} LU under the voice, "
                      f"gain {gain_db:+.1f} dB)[/]")
        track = under_narration(track, bed, gain_db)

    track.export(raw, format="wav")
    write_master(raw, master, config.sample_rate, target_lufs=config.volume_lufs,
                 announcement=f"Setting the volume to {config.volume_lufs:g} LUFS...",
                 on_failure="the mix as it was")
    write_json(fingerprint_path, _fingerprint(timing_path, config, bgm))
    console.print(f"[bold green]✓ Audio mixed:[/] {_esc(str(master))}")
    return master


def mix_long_audio(project_name: str, chapters: list[str], lengths: list[float], config: AudioConfig,
                   work: Path, out: Path) -> Path:
    """A long video's sound (workflow/long_video.py): every chapter's
    narration, each fitted to its picture's length, then ONE music bed under
    the whole of it and one volume over the result. Not the chapters' own
    masters end to end: each of those carries its own bed, so the song cut
    off and started again from its intro at every chapter change, whatever
    the loop pause (user report, 2026-10-26: at 3:00 of ch1-3.3 "the current
    looping background music just stop and another start")."""
    rate = config.sample_rate
    narration = work / "narration.wav"
    with wave.open(str(narration), "wb") as joined:
        joined.setnchannels(2)
        joined.setsampwidth(2)
        joined.setframerate(rate)
        for chapter, seconds in zip(chapters, lengths, strict=True):
            track = narration_track(project_name, chapter, config).set_sample_width(2)
            frames = round(seconds * rate)
            if track.frame_count() < frames:
                track += AudioSegment.silent(duration=(frames - track.frame_count()) * 1000 / rate + 50,
                                             frame_rate=rate)
            joined.writeframes(track.get_sample_slice(0, frames).raw_data)

    raw, bgm = narration, _bgm_file(config)
    bed_wav = work / "music_bed.wav"
    if bgm and write_music_bed(sum(lengths), load_bgm(bgm, rate), round(config.bgm_loop_gap_s * 1000), bed_wav):
        gain_db = music_gain_db(narration, bed_wav, config.bgm_below_voice_lu)
        console.print(f"[cyan]Adding background music across all {len(chapters)} chapters:[/] {_esc(str(bgm))} "
                      f"[dim](its loud parts {config.bgm_below_voice_lu:g} LU under the voice, "
                      f"gain {gain_db:+.1f} dB)[/]")
        raw = work / "sound_raw.wav"
        run_ffmpeg(["ffmpeg", "-y", "-i", str(narration), "-i", str(bed_wav), "-filter_complex",
                    f"[1:a]volume={gain_db:.2f}dB[m];[0:a][m]amix=inputs=2:normalize=0:duration=first",
                    "-c:a", "pcm_f32le", str(raw)], check=True, capture=True)
        narration.unlink(missing_ok=True)
    bed_wav.unlink(missing_ok=True)
    write_master(raw, out, rate, target_lufs=config.volume_lufs,
                 announcement=f"Setting the volume to {config.volume_lufs:g} LUFS...",
                 on_failure="the mix as it was")
    narration.unlink(missing_ok=True)
    return out
