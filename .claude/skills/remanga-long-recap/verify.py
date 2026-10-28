"""A project checked end to end, chapter by chapter - what is there, whole and right. Changes nothing
(a failing narration gets remanga's fix request, as Check narration does).

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/verify.py P [CHAPTERS] [--decode]

CHAPTERS like 1-5,7 (default: every chapter). Per chapter:
  pages      the download record says verified, its page count is on disk, every page decodes and is marked
  panels     every panel narration.json names is cut and decodes
  narration  Make video's own check (check_chapter) - ok, and still what the audio says
  audio      audio_manifest (every take's bytes + SHA-256), every take a whole WAV, and every take's whisper
             words aligned again against its script (>= align.MIN_MATCH_RATIO, 90%)
  video      video and audio streams the same length, as long as the narration, every packet readable,
             the sound decodes at about the Volume setting, no hidden .tmp beside it;
             --decode also decodes every frame (slow, CPU - leave it for when nothing renders)
Then each long video of these chapters, the same way. A page's bytes against MangaDex's checksums is
`./run.sh download -p P -c all` (it re-hashes every page and fetches any that fail). Exits 1 on a problem."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from remanga.audio.manifest import AudioManifestError, verify_audio_manifest
from remanga.chapters import discover_chapters, expand_chapter_selection
from remanga.config import RemangaConfig
from remanga.paths import get_chapter_dir, get_final_video_path, get_generated_dir, get_long_videos_dir, get_project_dir
from remanga.subtitles.align import MIN_MATCH_RATIO, align
from remanga.workflow.video import check_chapter

AV_SLACK = 0.1          # seconds video and audio may differ
TIMELINE_SLACK = 2.0    # seconds the video may differ from the narration timeline (plus any intro)
LOUDNESS_SLACK = 1.0    # LU from the Volume setting


def decodes(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.load()
        return True
    except Exception:  # any failure to read is the finding
        return False


def check_pages(project: str, chapter: str, record: dict) -> tuple[str, list[str]]:
    chapter_dir = get_chapter_dir(project, chapter)
    files = sorted(p for p in (chapter_dir / "pages").iterdir() if p.is_file() and not p.name.startswith("."))
    problems = []
    pages = record.get("pages") or {}
    if "verified" in pages and not pages["verified"]:
        problems.append("download not verified - run ./run.sh download")
    if pages.get("checks") and not all(pages["checks"].values()):
        problems.append(f"page checks failed: {pages['checks']}")
    if pages.get("total_pages") and pages["total_pages"] != len(files):
        problems.append(f"{len(files)} page files, the source lists {pages['total_pages']}")
    with ThreadPoolExecutor(4) as pool:
        broken = [f.name for f, ok in zip(files, pool.map(decodes, files), strict=True) if not ok]
    problems += [f"page {name} does not decode" for name in broken]
    crops = chapter_dir / "crops.json"
    if crops.exists():
        marked = {p["page_filename"] for p in json.loads(crops.read_text(encoding="utf-8"))["pages"]}
        problems += [f"page {f.name} has no marks entry" for f in files if f.name not in marked]
    else:
        problems.append("no crops.json")
    return f"{len(files)} pages", problems


def check_panels(project: str, chapter: str) -> tuple[str, list[str]]:
    chapter_dir = get_chapter_dir(project, chapter)
    path = chapter_dir / "narration.json"
    if not path.exists():
        return "not narrated", []
    rows = json.loads(path.read_text(encoding="utf-8"))["narration"]["panels"]
    files = [chapter_dir / "panels" / f"{row['panel']}.png" for row in rows if not row.get("skip")]
    with ThreadPoolExecutor(4) as pool:
        broken = [f.name for f, ok in zip(files, pool.map(lambda f: f.exists() and decodes(f), files), strict=True)
                  if not ok]
    return f"{len(files)} panels", [f"panel {name} missing or does not decode" for name in broken]


def whole_wav(path: Path) -> str | None:
    try:
        with wave.open(str(path)) as w:
            frames = w.getnframes()
            data = w.readframes(frames)
            if frames == 0:
                return "empty"
            if len(data) != frames * w.getnchannels() * w.getsampwidth():
                return f"truncated ({len(data)} of {frames * w.getnchannels() * w.getsampwidth()} bytes)"
    except (wave.Error, EOFError, OSError) as error:
        return str(error)
    return None


def check_audio(project: str, chapter: str) -> tuple[str, list[str], dict | None]:
    audio_dir = get_generated_dir(project, "audio", chapter, create=False)
    timing_path = audio_dir / "audio_timing.json"
    if not timing_path.exists():
        return "not narrated", [], None
    problems = []
    try:
        verify_audio_manifest(audio_dir, chapter)
    except AudioManifestError as error:
        problems.append(f"audio manifest: {error}")
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    texts = {row["panel_id"]: row["text"] for row in timing["panels"]}
    problems += [f"panel {row['panel_id']} has no sound" for row in timing["panels"] if not row.get("duration_ms")]
    subs_dir = get_generated_dir(project, "subtitles", chapter, create=False)
    ratios = []
    for batch in timing.get("batches") or []:
        take = audio_dir / f"{batch['name']}.wav"
        bad = whole_wav(take) if take.exists() else "missing"
        if bad:
            problems.append(f"take {take.name}: {bad}")
            continue
        words = subs_dir / f"{batch['name']}.json"
        if not words.exists():
            problems.append(f"take {batch['name']}: no whisper words")
            continue
        document = json.loads(words.read_text(encoding="utf-8"))
        ratio = align([(pid, texts[pid]) for pid in batch["panels"]], document["words"],
                      float(document["audio_duration_sec"])).match_ratio
        ratios.append(ratio)
        if ratio < MIN_MATCH_RATIO:
            problems.append(f"take {batch['name']}: only {ratio:.0%} of its script was heard")
    takes = len(timing.get("batches") or [])
    low = f", lowest match {min(ratios):.0%}" if ratios else ""
    return f"{takes} takes{low}", problems, timing


def probe(path: Path) -> dict[str, float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json",
                          str(path)], capture_output=True, text=True, check=False)
    streams = json.loads(out.stdout or "{}").get("streams", [])
    return {s["codec_type"]: float(s.get("duration") or 0) for s in streams}


def check_mp4(path: Path, volume: float, expected: float | None, decode: bool) -> tuple[str, list[str]]:
    problems = []
    durations = probe(path)
    video, audio = durations.get("video", 0.0), durations.get("audio", 0.0)
    if not video or not audio:
        return "", [f"{path.name}: streams {durations}"]
    if abs(video - audio) > AV_SLACK:
        problems.append(f"video {video:.2f} s but audio {audio:.2f} s")
    if expected is not None and abs(video - expected) > TIMELINE_SLACK:
        problems.append(f"video {video:.2f} s, the narration timeline {expected:.2f} s")
    packets = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries", "stream=nb_read_packets",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=False)
    if packets.returncode or packets.stderr.strip():
        problems.append(f"packets: {packets.stderr.strip()[:200] or packets.returncode}")
    sound = subprocess.run(["ffmpeg", "-nostats", "-v", "info", "-i", str(path), "-map", "0:a",
                            "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, check=False)
    found = re.findall(r"^\s+I:\s+(-?[\d.]+) LUFS", sound.stderr, re.MULTILINE)
    loudness = float(found[-1]) if found else None
    errors = [line for line in sound.stderr.splitlines() if re.search(r"error|invalid|corrupt", line, re.IGNORECASE)]
    if sound.returncode or errors:
        problems.append(f"sound does not decode cleanly: {(errors or [str(sound.returncode)])[0][:200]}")
    if loudness is None or abs(loudness - volume) > LOUDNESS_SLACK:
        problems.append(f"loudness {loudness} LUFS, Volume is {volume}")
    if decode:
        frames = subprocess.run(["ffmpeg", "-nostats", "-v", "error", "-i", str(path), "-map", "0:v", "-f", "null",
                                 "-"], capture_output=True, text=True, check=False)
        if frames.returncode or frames.stderr.strip():
            problems.append(f"video does not decode cleanly: {frames.stderr.strip()[:200] or frames.returncode}")
    problems += [f"hidden temp file {p.name}" for p in path.parent.iterdir() if p.name.startswith(".")
                 and p.name.endswith(".tmp")]
    minutes, seconds = divmod(round(video), 60)
    hours, minutes = divmod(minutes, 60)
    length = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
    return f"{length}, {loudness} LUFS", problems


def intro_seconds(path: Path) -> float:
    """How long the intro in front of a chapter's video is (final_intro.json names it, or null)."""
    info = path.parent / "_work" / "final_intro.json"
    intro = (json.loads(info.read_text(encoding="utf-8")) or {}).get("intro") if info.exists() else None
    return probe(Path(intro)).get("video", 0.0) if intro and Path(intro).exists() else 0.0


def verify_chapter(project: str, chapter: str, config: RemangaConfig, manifest: dict, decode: bool) -> list[str]:
    parts, problems = [], []
    done, found = check_pages(project, chapter, manifest.get("chapters", {}).get(chapter, {}))
    parts.append(done)
    problems += found
    done, found = check_panels(project, chapter)
    parts.append(done)
    problems += found
    result = check_chapter(project, chapter, config)
    parts.append(f"narration {result['state']}")
    if result["state"] == "problems":
        problems += result["errors"]
    done, found, timing = check_audio(project, chapter)
    parts.append(done)
    problems += found
    video = get_final_video_path(project, chapter, create=False)
    if video.exists():
        expected = float(timing["total_timeline_sec"]) + intro_seconds(video) if timing else None
        done, found = check_mp4(video, config.audio.volume_lufs, expected, decode)
        parts.append(f"video {done}")
        problems += found
    else:
        parts.append("no video")
    print(f"chapter {chapter}: " + " · ".join(parts) + (" · OK" if not problems else ""), flush=True)
    for line in problems:
        print(f"  - {line}", flush=True)
    return problems


def verify_long(project: str, chapters: list[str], config: RemangaConfig, decode: bool) -> list[str]:
    problems = []
    root = get_long_videos_dir(project)
    for info in sorted(root.glob("*/long.json")) if root.exists() else []:
        data = json.loads(info.read_text(encoding="utf-8"))
        joined = [str(c) for c in data.get("chapters") or []]
        if joined and not set(joined) & set(chapters):
            continue
        videos = sorted(p for p in info.parent.glob("*_recap.mp4"))
        if not videos:
            problems.append(f"{info.parent.name}: no video")
            continue
        done, found = check_mp4(videos[0], config.audio.volume_lufs, None, decode)
        print(f"long {info.parent.name}: {len(joined)} chapters · {done}" + (" · OK" if not found else ""), flush=True)
        for line in found:
            print(f"  - {line}", flush=True)
        problems += found
    return problems


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    project = args[0]
    every = discover_chapters(project)
    chapters = expand_chapter_selection(args[1], every) if len(args) > 1 else every
    config = RemangaConfig.load()
    manifest_path = get_project_dir(project) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    decode = "--decode" in sys.argv
    problems = []
    for chapter in chapters:
        problems += verify_chapter(project, str(chapter), config, manifest, decode)
    problems += verify_long(project, [str(c) for c in chapters], config, decode)
    print(f"{len(chapters)} chapter(s) checked - " + (f"{len(problems)} problem(s)" if problems else "all OK"))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
