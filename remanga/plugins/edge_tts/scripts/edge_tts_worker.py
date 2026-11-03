#!/usr/bin/env python3
"""Standalone Edge voices synthesis worker - runs inside the isolated
`.tools/venv-edge-tts` environment as a long-lived subprocess, spoken to by
remanga/audio/synth/ over line-delimited JSON on stdin/stdout. No dependency
on the `remanga` package.

edge-tts sends the text to Microsoft's Read Aloud service, splitting it into
pieces the service accepts itself, so one request can be a whole chapter. The
service answers in MP3 (24 kHz mono); the worker turns that into 16-bit PCM
WAV with ffmpeg, as every other engine writes. A dropped connection is tried
again a few times before the request fails.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "voice": ..., "text": ..., "output_path": ...}
  Worker -> parent (once ready): {"event": "ready"}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ATTEMPTS = 4
SAMPLE_RATE = 24000


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


async def _save(text: str, voice: str, mp3: Path) -> None:
    import edge_tts

    # The service's own pace - read raw, never sped up (no rate is sent).
    await edge_tts.Communicate(text, voice).save(str(mp3))


def synthesize(req: dict, ffmpeg: str) -> None:
    output = Path(req["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    mp3 = output.with_name(output.stem + ".edge.mp3")
    error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            asyncio.run(_save(req["text"], req["voice"], mp3))
            if mp3.exists() and mp3.stat().st_size > 0:
                break
            raise RuntimeError("the service sent no audio")
        except Exception as failure:  # network drops, throttling - try again
            error = failure
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"Edge voices failed after {ATTEMPTS} tries: {error}")
    partial = output.with_name(output.stem + ".partial.wav")
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(SAMPLE_RATE),
                    "-c:a", "pcm_s16le", str(partial)], check=True)
    partial.replace(output)
    mp3.unlink(missing_ok=True)


def main() -> None:
    try:
        import edge_tts  # noqa: F401 - fail now, not on the first request
    except Exception as e:
        send({"event": "error", "error": f"Failed to load edge-tts: {e}"})
        sys.exit(1)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        send({"event": "error", "error": "ffmpeg is not on PATH - the Edge voices worker needs it"})
        sys.exit(1)

    send({"event": "ready", "device": "online"})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            send({"ok": False, "error": f"Bad request JSON: {e}"})
            continue
        if req.get("cmd") == "shutdown":
            break
        try:
            synthesize(req, ffmpeg)
            send({"ok": True})
        except Exception as e:
            send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
