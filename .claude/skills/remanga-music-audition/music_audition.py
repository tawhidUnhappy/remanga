"""Hear background-music candidates the way a chapter mixes them, and measure what an ear would judge.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-music-audition/music_audition.py \
        PROJECT CHAPTER OUT_DIR TRACK [TRACK ...] [--seconds 50] [--start 0]

For each track: the chapter's real narration (no music) with the track as its bed, made exactly as
remanga's mix makes it - the bed looped across the WHOLE chapter and its loud parts measured over all
of it, set the configured LU under the voice (audio/mix.py:music_gain_db), the mix brought to the
Volume target - then the stretch from --start for --seconds. OUT_DIR gets N-name.mp3 per track,
ALL-in-a-row.mp4 (one card per track naming it), scores.json and what-they-say.txt.

Measured on each track alone (an ear would hear these, Claude cannot):
  words     - what whisper hears in it: a bed with words sung in it fights the narrator (want 0)
  onsets/s  - sharp attacks a second (spectral flux peaks): drums and plucks tick against speech
  speech %  - the share of its energy in 1-4 kHz, where speech is understood: music there masks words
  LRA       - EBU loudness range: a wide one is lost under the voice in its quiet parts
  centroid  - spectral centroid in Hz: lower is warmer
Run with nothing else on the GPU (whisper). config.json is read, never saved."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np

from remanga.audio.master import load_bgm, music_bed, under_narration, write_master
from remanga.audio.mix import music_gain_db, narration_track
from remanga.audio.resample import load_audio
from remanga.config import RemangaConfig
from remanga.ffmpeg_io import run_ffmpeg
from remanga.plugins.faster_whisper.transcribe import Transcriber
from remanga.workflow.voice_video import labelled_video

RATE = 22050


def short_name(track: Path) -> str:
    stem = re.sub(r"\s*\[[^\]]*\]", "", track.stem)          # drop "[video id]" tags
    return re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")[:40] or "track"


def mono(path: Path) -> np.ndarray:
    seg = load_audio(path, RATE, channels=1)
    return np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0


def spectral(x: np.ndarray) -> dict:
    """Onsets a second, the speech-band share of the energy and the centroid, over 2048-sample frames."""
    frame, hop = 2048, 512
    window = np.hanning(frame)
    frames = np.lib.stride_tricks.sliding_window_view(x, frame)[::hop] * window
    mag = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(frame, 1 / RATE)
    power = mag ** 2
    loud = power.sum(axis=1) > np.percentile(power.sum(axis=1), 20)   # skip near-silence
    band = (freqs >= 1000) & (freqs <= 4000)
    speech = float(power[loud][:, band].sum() / max(power[loud].sum(), 1e-12))
    centroid = float(np.median((mag[loud] * freqs).sum(axis=1) / np.maximum(mag[loud].sum(axis=1), 1e-12)))
    flux = np.maximum(np.diff(np.log1p(mag), axis=0), 0).sum(axis=1)
    peaks = (flux[1:-1] > flux[:-2]) & (flux[1:-1] >= flux[2:]) & (flux[1:-1] > np.median(flux) * 3)
    seconds = len(x) / RATE
    return {"onsets_per_s": round(float(peaks.sum()) / seconds, 2), "speech_band_pct": round(100 * speech, 1),
            "centroid_hz": round(centroid)}


def loudness_range(path: Path) -> float | None:
    result = run_ffmpeg(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                        capture=True)
    found = re.findall(r"LRA:\s+(-?[\d.]+) LU", result.stderr or "")
    return float(found[-1]) if found else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("chapter")
    parser.add_argument("out", type=Path)
    parser.add_argument("tracks", nargs="+", type=Path)
    parser.add_argument("--seconds", type=float, default=50.0)
    parser.add_argument("--start", type=float, default=0.0)
    args = parser.parse_args()
    config = RemangaConfig.load()   # read only - never saved
    audio = config.audio
    args.out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="music-audition-"))
    try:
        voice = narration_track(args.project, args.chapter, audio)
        voice_wav = work / "voice.wav"
        voice.export(voice_wav, format="wav")
        start_ms, end_ms = int(args.start * 1000), int((args.start + args.seconds) * 1000)
        rows, samples = [], []
        transcriber = Transcriber(config.subtitles)
        try:
            for n, track in enumerate(args.tracks, 1):
                name = short_name(track)
                bed = music_bed(voice, load_bgm(track, audio.sample_rate), gap_ms=round(audio.bgm_loop_gap_s * 1000))
                bed_wav = work / f"bed_{n}.wav"
                bed.export(bed_wav, format="wav")
                gain = music_gain_db(voice_wav, bed_wav, audio.bgm_below_voice_lu)
                mixed = under_narration(voice, bed, gain)[start_ms:end_ms]
                raw, final = work / f"mix_{n}.wav", args.out / f"_mix_{n}.wav"
                mixed.export(raw, format="wav")
                write_master(raw, final, audio.sample_rate, target_lufs=audio.volume_lufs)
                run_ffmpeg(["ffmpeg", "-y", "-i", str(final), "-c:a", "libmp3lame", "-q:a", "2",
                            str(args.out / f"{n}-{name}.mp3")], check=True, capture=True)
                alone = work / f"alone_{n}.wav"
                load_audio(track, 16000, channels=1).export(alone, format="wav")
                words_json = work / f"words_{n}.json"
                transcriber.words_for(alone, words_json)
                words = [w for w in json.loads(words_json.read_text())["words"] if w.get("probability", 0) >= 0.5]
                stats = {"words": len(words), **spectral(mono(track)), "lra": loudness_range(track),
                         "gain_db": gain}
                rows.append({"n": n, "name": name, "file": str(track), **stats,
                             "heard": " ".join(w["word"].strip() for w in words)[:120]})
                samples.append((name, f"{stats['words']} words, {stats['onsets_per_s']} onsets/s, "
                                      f"{stats['speech_band_pct']}% speech band, LRA {stats['lra']}", final))
        finally:
            transcriber.shutdown()
        labelled_video(samples, f"Background music under chapter {args.chapter}'s narration",
                       args.out / "ALL-in-a-row.mp4", audio.sample_rate)
        (args.out / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        lines = [f"Each sample: chapter {args.chapter}'s narration from {args.start:g} s for {args.seconds:g} s, the "
                 f"track {audio.bgm_below_voice_lu:g} LU under it (by its loud parts over the whole chapter), the "
                 f"mix at {audio.volume_lufs:g} LUFS - as the video will sound.", ""]
        lines += [f"{r['n']}-{r['name']}.mp3 - {r['file']}\n    {r['words']} words heard"
                  + (f" ({r['heard']!r})" if r["heard"] else "")
                  + f", {r['onsets_per_s']} onsets/s, {r['speech_band_pct']}% of its energy in 1-4 kHz, "
                    f"centroid {r['centroid_hz']} Hz, LRA {r['lra']} LU" for r in rows]
        (args.out / "what-they-say.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for f in args.out.glob("_mix_*.wav"):
            f.unlink()
        print("\n".join(lines))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
