"""An intro in front of every recap: chosen like the background music
(Settings - Intro, from global/intro/), off by default.

The intro is re-encoded once into a "leader" that matches the chapter's own
picture and sound - same size, frame rate, encoder and settings, colour tags,
sample rate - and cached in the chapter's work folder. The leader and the
recap are then joined by stream copy, so adding an intro never re-encodes a
chapter. Stream copy is only safe when the two streams' parameter sets match
byte for byte (encoding.stream_signature); when they do not, the join is
re-encoded instead of risking a file that breaks where the recap begins.
"""

from __future__ import annotations

import json
from pathlib import Path

from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json_or, write_json
from remanga.video.encoding import (
    AUDIO_CODEC_ARGS,
    COLOR_TAG_ARGS,
    MAX_KEYFRAME_INTERVAL_SEC,
    MUX_ARGS,
    picture_codec_args,
    stream_signature,
)

INTRO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}


def chosen_intro(video_config) -> Path | None:
    """The intro file the settings ask for, or None (off, or not a file)."""
    if not video_config.intro_enabled or not video_config.intro_path:
        return None
    path = Path(str(video_config.intro_path)).expanduser()
    if not path.is_file():
        console.print(f"[yellow]The intro is on, but '{_esc(str(path))}' isn't a file - rendering without it.[/]")
        return None
    return path


def intro_identity(video_config) -> dict | None:
    """What decides the intro part of a finished video - compared on every
    render, so switching the intro (or off) re-joins it."""
    path = chosen_intro(video_config)
    if path is None:
        return None
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _probe(path: Path, entries: str, stream: str) -> dict:
    result = run_ffmpeg(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries,
                         "-of", "json", str(path)], capture=True)
    try:
        streams = json.loads(result.stdout or "{}").get("streams", [])
    except ValueError:
        streams = []
    return streams[0] if streams else {}


def _duration(path: Path) -> float:
    result = run_ffmpeg(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                        capture=True)
    try:
        return float((result.stdout or "0").strip())
    except ValueError:
        return 0.0


def leader(renderer, intro: Path, body: Path, work_dir: Path) -> Path:
    """The intro re-encoded to match `body` (the finished recap), cached."""
    video = renderer.video_config
    ffmpeg_bin, codec, use_gpu, _ = renderer.encoder()
    sound = _probe(body, "stream=sample_rate,channels", "a:0")
    rate, channels = int(sound.get("sample_rate", 44100)), int(sound.get("channels", 2))
    key = {"intro": intro_identity(video), "width": video.width, "height": video.height, "fps": video.fps,
           "codec": codec, "gpu": use_gpu, "rate": rate, "channels": channels, "version": 1}
    out = work_dir / "intro_leader.mp4"
    stamp = work_dir / "intro_leader.json"
    if out.exists() and read_json_or(stamp, None) == key:
        return out

    seconds = _duration(intro)
    frames = max(1, round(seconds * video.fps))
    has_audio = bool(_probe(intro, "stream=codec_type", "a:0"))
    fit = (f"fps={video.fps},scale={video.width}:{video.height}:force_original_aspect_ratio=decrease,"
           f"pad={video.width}:{video.height}:(ow-iw)/2:(oh-ih)/2:black,"
           "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")
    cmd = [ffmpeg_bin, "-y", "-i", str(intro)]
    if not has_audio:  # a silent intro still needs a sound track to join onto the recap's
        cmd += ["-f", "lavfi", "-i", f"anullsrc=r={rate}:cl={'stereo' if channels == 2 else 'mono'}"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
            "-vf", fit, *COLOR_TAG_ARGS, "-bf", "0", "-g", str(video.fps * MAX_KEYFRAME_INTERVAL_SEC),
            "-frames:v", str(frames), *picture_codec_args(codec, use_gpu, renderer.system_config.threads),
            *AUDIO_CODEC_ARGS, "-ar", str(rate), "-ac", str(channels), "-t", f"{frames / video.fps:.3f}",
            *MUX_ARGS, str(out)]
    console.print(f"[cyan]Preparing the intro[/] [dim]({_esc(intro.name)}, {seconds:.1f}s, "
                  f"{video.width}x{video.height} at {video.fps}fps)[/]")
    result = run_ffmpeg(cmd, capture=True)
    if result.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"Could not prepare the intro {intro}:\n{result.stderr[-1500:]}")
    write_json(stamp, key)
    return out


def join(renderer, intro_part: Path, body: Path, out: Path) -> None:
    """`intro_part` then `body` into `out` - stream copy when the pictures
    match exactly, otherwise one re-encode of the whole."""
    same = stream_signature(intro_part) is not None and stream_signature(intro_part) == stream_signature(body)
    if same:
        listing = out.with_suffix(".txt")
        listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in (intro_part, body)),
                           encoding="utf-8")
        result = run_ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                             "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", *MUX_ARGS, str(out)], capture=True)
        listing.unlink(missing_ok=True)
    else:
        console.print("[dim](the intro's stream differs from the recap's - joining by re-encoding)[/]")
        ffmpeg_bin, codec, use_gpu, _ = renderer.encoder()
        total = _duration(intro_part) + _duration(body)
        result = run_ffmpeg([ffmpeg_bin, "-y", "-i", str(intro_part), "-i", str(body), "-filter_complex",
                             "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
                             *COLOR_TAG_ARGS, "-bf", "0",
                             *picture_codec_args(codec, use_gpu, renderer.system_config.threads),
                             *AUDIO_CODEC_ARGS, *MUX_ARGS, str(out)],
                            capture=True, show_progress=True, total_seconds=total, description="Adding the intro")
    if result.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"Could not add the intro:\n{result.stderr[-1500:]}")
