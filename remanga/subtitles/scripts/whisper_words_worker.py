#!/usr/bin/env python3
"""Standalone faster-whisper worker - runs inside the isolated
`.tools/venv-faster-whisper` environment as a long-lived subprocess, spoken
to by remanga/subtitles/ (in the main env) over a line-delimited JSON
protocol on stdin/stdout. Deliberately has ZERO dependency on the `remanga`
package itself - only `faster-whisper` and the stdlib - for the same reason
kokoro_worker.py and qwen_tts_worker.py don't.

What it is for: Qwen3-TTS returns audio and nothing else, so once a chapter
is narrated in a few long takes there is no longer anything that says where
one panel's line stops and the next begins. This reads that back off the
audio as word timings, which remanga/subtitles/align.py then matches against
the narration it asked for.

Transcription settings that are deliberate, not defaults:
  condition_on_previous_text=False  Whisper is a language model and will
      happily continue a loop it has started. Over a nine-minute take that
      is how a run of similar sentences becomes the same sentence eight
      times, with timings to match.
  vad_filter=False  The VAD drops audio it judges non-speech. Here that is
      a way to lose a real word - and a lost word is a panel boundary that
      has to be guessed.
  word_timestamps=True  The whole point.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "transcribe", "audio_path": ..., "output_path": ...}
  Worker -> parent (once ready): {"event": "ready", "device": ...}
  Worker -> parent (per request): {"ok": true, "words": N, "duration": S}
                                  or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

Every model call runs with stdout redirected to a buffer so library prints
can't corrupt the protocol, and TQDM_DISABLE is set before anything imports
tqdm - the parent keeps stderr's last lines for its error messages, and a
real failure would otherwise be reported as a screen of progress bars.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import warnings
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")

real_stdout = sys.stdout
warnings.filterwarnings("ignore")


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    # Either a directory of converted weights or a name faster-whisper
    # knows ("large-v3"), which it fetches into the Hub cache itself.
    parser.add_argument("--model", required=True)
    parser.add_argument("--language", default="en")
    parser.add_argument("--compute_type", default="float16")
    args = parser.parse_args()

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import ctranslate2
            from faster_whisper import WhisperModel

            # ctranslate2, not torch: this environment has no torch in it on
            # purpose (faster-whisper runs on CTranslate2), and asking the
            # wrong library whether there is a GPU is how that gets undone.
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            # float16 is a GPU format; on CPU it is both unsupported and
            # pointless, so the CPU path takes int8 whatever was asked for.
            compute_type = args.compute_type if device == "cuda" else "int8"
            model = WhisperModel(args.model, device=device, compute_type=compute_type)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load faster-whisper: {e}"})
        sys.exit(1)

    send({"event": "ready", "device": device})

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
            output_path = Path(req["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with contextlib.redirect_stdout(io.StringIO()):
                segments, info = model.transcribe(
                    str(Path(req["audio_path"])),
                    language=args.language,
                    word_timestamps=True,
                    condition_on_previous_text=False,
                    vad_filter=False,
                )
                # `segments` is a generator - nothing runs until it is walked.
                words = [
                    {"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3),
                     "probability": round(w.probability, 4)}
                    for segment in segments for w in (segment.words or [])
                ]

            if not words:
                raise RuntimeError("faster-whisper returned no words for this audio")

            document = {
                "audio_file": Path(req["audio_path"]).name,
                "language": info.language,
                "audio_duration_sec": round(info.duration, 3),
                "words": words,
            }
            tmp_path = output_path.with_name(output_path.name + ".tmp")
            tmp_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
            tmp_path.replace(output_path)

            send({"ok": True, "words": len(words), "duration": round(info.duration, 3)})
        except Exception as e:
            # str() of a bare AssertionError is empty - fall back to the type.
            send({"ok": False, "error": str(e) or type(e).__name__})


if __name__ == "__main__":
    main()
