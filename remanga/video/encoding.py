"""How a recap's picture and sound are encoded - in one place, because two
callers have to agree to the byte: a chapter render writes each chapter's
picture stream, and the full-recap join stream-copies those streams end to
end, which only works when every chapter was encoded identically.

Measured on a real 71-panel, 7.6-minute chapter (RTX 3060, Ryzen 5 5600G);
quality is PSNR of the decoded video against the composited source frames:

    before  30fps  NVENC p6 CQ20, BT.601 untagged          65.5s  56.5dB
            30fps  libx264 medium CRF19, 4 threads         95.7s  53.3dB
    now      5fps  NVENC p4 CQ18, BT.709 tagged             7.8s  56.0dB
             5fps  NVENC p6 CQ18                           13.7s  55.0dB
             5fps  libx264 slow stillimage CRF18, 12 thr   22.1s  56.1dB

Every one of those is far past visually lossless (~45dB)."""

from __future__ import annotations

import json
from pathlib import Path

from remanga.ffmpeg_io import run_ffmpeg
from remanga.video.frame_timeline import FrameTimeline

# Bumped whenever a change here alters what a picture stream contains, so a
# picture cached by an older remanga is re-encoded rather than reused - or
# stream-copied into a join next to pictures it no longer matches.
PICTURE_FORMAT_VERSION = 1

# A keyframe at least this often, on top of the one forced at every panel
# change. Nothing moves in between, so a long interval costs nothing but a
# slower seek into the middle of an unusually long panel.
MAX_KEYFRAME_INTERVAL_SEC = 60

# ffmpeg's own documentation of the `fast` AAC coder: "Worse with low
# bitrates (less than 64kbps), but is better and much faster at higher
# bitrates" - and 192k is well above that. 3.2s instead of 9.4s for 7.6
# minutes of audio, which had become the slowest part of a render once the
# picture got cheap.
AUDIO_CODEC_ARGS = ("-c:a", "aac", "-aac_coder", "fast", "-b:a", "192k")

# The MP4 index at the front of the file, so a player or an upload can start
# before reading to the end.
MUX_ARGS = ("-movflags", "+faststart")

# BT.709, and tagged as such - what every player assumes for HD. The untagged
# BT.601 conversion renders used to get played back with subtly shifted color.
COLOR_TAG_ARGS = ("-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv")


def picture_filter_args(timeline: FrameTimeline) -> list[str]:
    """Everything about a picture stream except which encoder writes it."""
    args = [
        "-vf", f"fps={timeline.fps},scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
        *COLOR_TAG_ARGS,
        # No B-frames: nothing to predict between stills, and without a decode
        # delay there's no edit list for the MP4 to carry.
        "-bf", "0",
        "-g", str(timeline.fps * MAX_KEYFRAME_INTERVAL_SEC),
        # Exactly the timeline's length. Uncapped, the concat demuxer's
        # trailing entry made a real chapter's picture 6.4s longer than its
        # narration.
        "-frames:v", str(timeline.total_frames),
    ]
    keyframes = timeline.keyframe_times()
    if keyframes:
        args += ["-force_key_frames", keyframes]
    return args


def picture_codec_args(codec: str, use_gpu: bool, threads: int) -> list[str]:
    """The encoder and its quality settings (see the table above)."""
    if use_gpu and codec.endswith("_nvenc"):
        # Constant quality with no bitrate ceiling; -forced-idr makes each
        # forced keyframe a true IDR, a clean entry point at every panel.
        args = ["-c:v", codec, "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0", "-forced-idr", "1"]
        if codec == "h264_nvenc":
            args += ["-profile:v", "high"]
        return args
    if use_gpu:
        # VideoToolbox/VAAPI have option sets of their own and were never
        # measured here, so they keep their defaults rather than guesses.
        return ["-c:v", codec]
    if codec == "libx264":
        return ["-c:v", codec, "-preset", "slow", "-tune", "stillimage", "-crf", "18", "-threads", str(threads)]
    return ["-c:v", codec, "-preset", "medium", "-crf", "19", "-threads", str(threads)]


def stream_signature(path: Path) -> str | None:
    """What two picture streams must share for one to be stream-copied onto
    the end of the other: the codec's parameter sets byte for byte
    (extradata), and the geometry and timing the container stores beside
    them. None when the file can't be probed."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_data_hash", "sha256",
        "-show_entries", "stream=codec_name,profile,level,width,height,pix_fmt,r_frame_rate,time_base,extradata_hash",
        "-of", "json", str(path),
    ]
    result = run_ffmpeg(cmd, capture=True)
    if result.returncode != 0:
        return None
    try:
        streams = json.loads(result.stdout or "{}").get("streams", [])
    except ValueError:
        return None
    return json.dumps(streams[0], sort_keys=True) if streams else None
