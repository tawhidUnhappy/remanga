#!/usr/bin/env python3
"""Standalone Ming-3.0-tts synthesis worker - runs inside the isolated
`.tools/venv-ming-tts` environment as a long-lived subprocess, spoken to by
remanga/audio/synth/ over line-delimited JSON on stdin/stdout. No dependency
on the `remanga` package: upstream's modules come from `--src_dir` (the
source setup.py fetched), the weights from `--model_dir`.

Every request is upstream's "IP" task - one of its built-in voices, with a
zero speaker embedding and no reference recording. MingTTS.synthesize splits
the text into short fragments, reads each and joins them, trimming each
fragment's trailing silence to 0.3s, so one request can be a whole chapter.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "voice": ..., "text": ..., "output_path": ...}
  Worker -> parent (once ready): {"event": "ready"}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

Model calls run with stdout redirected, so nothing they print can corrupt
the protocol; only `send` reaches the parent."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import warnings
from pathlib import Path

real_stdout = sys.stdout
warnings.filterwarnings("ignore")


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--src_dir", required=True)
    args = parser.parse_args()

    sys.path.insert(0, args.src_dir)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import soundfile as sf
            import torch
            from loguru import logger
            from ming_tts import MingTTS

            # loguru logs every fragment to stderr; the parent keeps only a
            # tail of it for error reports, so warnings and up are enough.
            logger.remove()
            logger.add(sys.stderr, level="WARNING")
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            model = MingTTS(args.model_dir, device=device)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load Ming-3.0-tts: {e}"})
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
                waveform = model.synthesize(
                    task="IP", text=req["text"], controls={"ip": req["voice"]},
                    use_zero_spk_emb=True,
                )
            # 16-bit PCM, as every other engine writes: upstream's own save is
            # 32-bit float, which the stdlib `wave` reader remanga measures
            # takes with cannot open.
            sf.write(str(output_path), waveform.squeeze(0).float().cpu().numpy(),
                     model.sample_rate, subtype="PCM_16")
            if not output_path.exists():
                raise RuntimeError("synthesis returned without writing an output file")
            send({"ok": True})
        except Exception as e:
            send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
