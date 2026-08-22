#!/usr/bin/env python3
"""Standalone IndexTTS-2.5 synthesis worker - runs inside the isolated
`.venv-indextts` environment as a long-lived subprocess, spoken to by
remanga/audio/synth.py (in the main env) over a line-delimited JSON protocol
on stdin/stdout. Deliberately has ZERO dependency on the `remanga` package
itself - only `indextts` and the stdlib - so it works regardless of what's
importable in the caller's environment.

Why a persistent worker instead of one process per line: loading the model
onto the GPU takes real time, and a chapter can have 100+ panels - reloading
per panel would make synthesis dramatically slower. This process is spawned
once per `remanga tts` run and handles every panel in that run.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "spk_audio_prompt": ..., "text": ...,
                     "lang": ..., "output_path": ..., "emo_vector": [...],
                     "temperature": ..., "top_p": ..., "duration_factor": ...}
  Worker -> parent (once ready): {"event": "ready"}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

IndexTTS2.infer() itself prints several unconditional lines directly to
stdout - those would corrupt this protocol if left alone, so every model call
happens with stdout redirected to a buffer; only this script's own explicit
protocol writes (via the `real_stdout` handle captured before any redirect)
reach the parent.
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import sys
from pathlib import Path

real_stdout = sys.stdout


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cfg_path", required=True)
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--use_bf16", action="store_true")
    args = parser.parse_args()

    try:
        try:
            from indextts.infer_v2_5 import IndexTTS2
        except ImportError:
            from indextts.infer_v2 import IndexTTS2  # older checkout fallback

        with contextlib.redirect_stdout(io.StringIO()):
            sig_params = inspect.signature(IndexTTS2.__init__).parameters
            kwargs = {"cfg_path": args.cfg_path, "model_dir": args.model_dir}
            if "use_bf16" in sig_params:
                kwargs["use_bf16"] = args.use_bf16
            model = IndexTTS2(**kwargs)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load IndexTTS: {e}"})
        sys.exit(1)

    send({"event": "ready"})

    infer_params = inspect.signature(model.infer).parameters

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
            call_kwargs = {
                "spk_audio_prompt": req["spk_audio_prompt"],
                "text": req["text"],
                "lang": req.get("lang", "EN"),
                "output_path": req["output_path"],
            }
            emo_vector = req.get("emo_vector")
            if emo_vector is not None:
                if "emo_vector" in infer_params:
                    call_kwargs["emo_vector"] = emo_vector
                elif "emotion_vector" in infer_params:
                    call_kwargs["emotion_vector"] = emo_vector

            has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in infer_params.values())
            if req.get("temperature") is not None and ("temperature" in infer_params or has_var_kwargs):
                call_kwargs["temperature"] = req["temperature"]
            if req.get("top_p") is not None and ("top_p" in infer_params or has_var_kwargs):
                call_kwargs["top_p"] = req["top_p"]
            if req.get("duration_factor") is not None and "duration_factor" in infer_params:
                call_kwargs["duration_factor"] = req["duration_factor"]

            with contextlib.redirect_stdout(io.StringIO()):
                model.infer(**call_kwargs)

            if not Path(req["output_path"]).exists():
                raise RuntimeError("infer() returned without writing an output file")

            send({"ok": True})
        except Exception as e:
            send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
