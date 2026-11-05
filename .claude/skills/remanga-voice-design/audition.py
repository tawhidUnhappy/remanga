"""Audition described narrator voices for Fish Audio Drama 3: each candidate reads the same text the
way a chapter is read (from its own voice file, a sentence per request), then every reading is
measured, ranked against target ranges and played in one labelled video.

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-voice-design/audition.py CANDIDATES.json TEXT.txt OUT_DIR

CANDIDATES.json - a list, in the order to play them:
    [{"name": "velvet_storyteller", "cue": "[velvety, slightly deep young man's voice, calm]",
      "seed": 1, "what": "short description for the card"}, ...]
A name already in DRAMA_VOICES is read in that voice (the cue in the code wins - with the seed it is
what the voice file was made from). Run from the remanga repo root; config.json is read, never saved.
OUT_DIR gets N-name.mp3 per reading, ALL-in-a-row.mp4 (one card per reading), what-they-say.txt and
scores.json; the raw takes and word timings stay in OUT_DIR/_work, so a re-run only measures again.
Targets (optional, a JSON object as the 4th argument) default to TARGETS below."""

from __future__ import annotations

import difflib
import itertools
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

from remanga.audio.hums import find_hums
from remanga.audio.master import write_master
from remanga.audio.resample import load_audio
from remanga.audio.synth import create_synthesizer
from remanga.config import RemangaConfig
from remanga.ffmpeg_io import run_ffmpeg
from remanga.plugins.drama3 import config as drama
from remanga.plugins.faster_whisper.transcribe import Transcriber
from remanga.subtitles.normalize import words as normalize
from remanga.workflow.voice_video import labelled_video

RATE = 16000
# A calm recap narrator, measured on recap channels: median pitch (Hz), the 5th-95th percentile
# pitch span (semitones - how much the voice moves), syllables a second over the whole reading
# (pauses included), and the typical pause between phrases (ms, median of gaps of 250 ms or more).
TARGETS = {"pitch_hz": [95, 118], "movement_st": [7.8, 12.5], "syllables_per_s": [4.35, 5.06],
           "pause_ms": [465, 715]}


def key_of(c: dict) -> str:
    return f"{c['name']}-seed{c.get('seed', 1)}"


def samples(path: Path) -> np.ndarray:
    seg = load_audio(path, RATE, channels=1)
    return np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0


def pitch_track(x: np.ndarray) -> np.ndarray:
    """F0 (Hz) of every voiced 40 ms frame, by normalized autocorrelation (60-350 Hz)."""
    frame, hop = 640, 160
    lo, hi = RATE // 350, RATE // 60
    frames = [x[i:i + frame] for i in range(0, len(x) - frame, hop)]
    if not frames:
        return np.array([])
    energy = np.array([np.sqrt(np.mean(f * f)) for f in frames])
    loud = np.percentile(energy, 90)
    window = np.hanning(frame)
    f0 = []
    for f, e in zip(frames, energy, strict=True):
        if e < loud * 10 ** (-25 / 20):
            continue
        f = (f - f.mean()) * window
        spec = np.fft.rfft(f, 2 * frame)
        ac = np.fft.irfft(spec * np.conj(spec))[:frame]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] < 0.5:
            continue
        a, b, c = ac[lag - 1], ac[lag], ac[min(lag + 1, len(ac) - 1)]
        shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        f0.append(RATE / (lag + shift))
    return np.array(f0)


def syllables(text: str) -> int:
    count = 0
    for word in re.findall(r"[a-z']+", text.lower()):
        groups = re.findall(r"[aeiouy]+", word)
        n = len(groups)
        if word.endswith("e") and not word.endswith(("le", "ee", "ye")) and n > 1:
            n -= 1
        count += max(1, n)
    return count


def measure(text: str, wav: Path, words_json: Path) -> dict:
    heard = json.loads(words_json.read_text(encoding="utf-8"))["words"]
    x = samples(wav)
    f0 = pitch_track(x)
    script = [t for w in text.split() for t in normalize(w)]
    said = [t for w in heard for t in normalize(str(w.get("word", "")))]
    match = difflib.SequenceMatcher(a=script, b=said, autojunk=False)
    matched = sum(block.size for block in match.get_matching_blocks())
    timed = [w for w in heard if w["end"] > w["start"]]
    gaps = [b["start"] - a["end"] for a, b in itertools.pairwise(timed)]
    pauses = [g for g in gaps if g >= 0.25]
    spoken = (timed[-1]["end"] - timed[0]["start"]) if timed else 0.0
    return {
        "seconds": round(len(x) / RATE, 1),
        "chars_per_s": round(len(text) / max(spoken, 0.1), 1),
        "syllables_per_s": round(syllables(text) / max(spoken, 0.1), 2),
        "pitch_hz": round(float(np.median(f0)), 1) if len(f0) else None,
        "movement_st": round(float(12 * np.log2(np.percentile(f0, 95) / np.percentile(f0, 5))), 1)
        if len(f0) > 10 else None,
        "pause_ms": round(float(np.median(pauses)) * 1000) if pauses else None,
        "pauses": len(pauses),
        "longest_pause_ms": round(max(gaps) * 1000) if gaps else None,
        "heard_pct": round(100 * matched / max(len(script), 1), 1),
        "hums": len(find_hums(wav, heard)),
    }


def distance(stats: dict, targets: dict) -> float:
    """How far a reading sits outside the target ranges, each range's width = 1; a word whisper did
    not hear and a hum each count more than any range."""
    total = 0.0
    for name, (low, high) in targets.items():
        value = stats.get(name)
        if value is None:
            total += 1.0
            continue
        total += max(0.0, low - value, value - high) / (high - low)
    return round(total + 0.2 * max(0.0, 99.0 - stats["heard_pct"]) + 0.5 * stats["hums"], 2)


def main() -> None:
    candidates = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    text = " ".join(Path(sys.argv[2]).read_text(encoding="utf-8").split())
    out = Path(sys.argv[3])
    targets = json.loads(sys.argv[4]) if len(sys.argv) > 4 else TARGETS
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)

    config = RemangaConfig.load()  # read only - never saved
    config.tts.engine = "drama3"
    for c in candidates:
        if c["name"] not in drama.VOICE_BY_NAME:
            drama.VOICE_BY_NAME[c["name"]] = drama.DramaVoice(c["name"], c["name"], c["cue"], c.get("what", ""))

    todo = [c for c in candidates if not (work / f"{key_of(c)}.wav").is_file()]
    if todo:
        synth = create_synthesizer(config.tts, config.audio)
        synth.use_whole_text()  # one take, as a chapter's page is read (the worker splits sentences itself)
        synth.ensure_ready()
        try:
            for c in todo:
                config.tts.drama3.seed = int(c.get("seed", 1))
                print(f"reading {key_of(c)} ...", flush=True)
                synth.synthesize(text, work / f"{key_of(c)}.wav", voice=c["name"])
        finally:
            synth.shutdown()

    transcriber = Transcriber(config.subtitles)
    try:
        for c in candidates:
            words = work / f"{key_of(c)}.words.json"
            if not words.is_file():
                transcriber.words_for(work / f"{key_of(c)}.wav", words)
    finally:
        transcriber.shutdown()

    rows = []
    for n, c in enumerate(candidates, 1):
        stats = measure(text, work / f"{key_of(c)}.wav", work / f"{key_of(c)}.words.json")
        cue = drama.VOICE_BY_NAME[c["name"]].cue
        rows.append({"n": n, "key": key_of(c), "name": c["name"], "seed": int(c.get("seed", 1)), "cue": cue,
                     "what": c.get("what", ""), **stats, "distance": distance(stats, targets)})
        # One measured gain to -14 LUFS (never single-pass loudnorm: it pumps between sentences).
        # write_master consumes its input, so it gets a copy - the take itself is kept.
        level = work / f"{key_of(c)}.level.wav"
        copy = work / f"{key_of(c)}.copy.wav"
        shutil.copy2(work / f"{key_of(c)}.wav", copy)
        write_master(copy, level, config.audio.sample_rate, target_lufs=-14.0)
        run_ffmpeg(["ffmpeg", "-y", "-i", str(level), "-c:a", "libmp3lame", "-q:a", "2",
                    str(out / f"{n}-{key_of(c)}.mp3")], check=True, capture=True)

    def card(r: dict) -> str:
        # The card prints 60 characters of it (workflow/voice_video.py).
        return (f"{r['pitch_hz']} Hz, {r['movement_st']} st, {r['syllables_per_s']} syl/s, "
                f"pauses {r['pause_ms']} ms, heard {r['heard_pct']}%")

    labelled_video([(f"{r['key']}", card(r), work / f"{r['key']}.wav") for r in rows],
                   "Drama 3 narrator audition", out / "ALL-in-a-row.mp4", config.audio.sample_rate)
    (out / "scores.json").write_text(json.dumps({"targets": targets, "text": text, "rows": rows}, indent=1),
                                     encoding="utf-8")
    lines = ["Fish Audio Drama 3 - described narrator voices, each read from its own voice file exactly as a",
             "chapter is read. Every sample reads:", "", text, "",
             f"Targets: {json.dumps(targets)}", "",
             "ALL-in-a-row.mp4 plays them in this order, each under a card naming it (sorted best-first below):", ""]
    lines += [f"{r['n']}-{r['key']}.mp3 - {r['what']}\n    cue {r['cue']}; {r['seconds']} s, {card(r)}, "
              f"{r['hums']} hum(s), distance {r['distance']}" for r in rows]
    lines += ["", "Ranked (distance from the targets, lower is closer):"]
    lines += [f"  {r['distance']:>5}  {r['key']}" for r in sorted(rows, key=lambda r: r["distance"])]
    (out / "what-they-say.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-len(rows) - 1:]))


if __name__ == "__main__":
    main()
