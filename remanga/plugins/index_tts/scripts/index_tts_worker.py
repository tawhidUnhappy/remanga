#!/usr/bin/env python3
"""Standalone IndexTTS-2.5 synthesis worker - runs inside the isolated
`.tools/venv-index-tts` environment as a long-lived subprocess, spoken to by
remanga/plugins/index_tts/synth.py (in the main env) over a line-delimited
JSON protocol on stdin/stdout. Deliberately has ZERO dependency on the
`remanga` package itself - only `indextts` and the stdlib - for the same
reason kokoro_worker.py doesn't.

Every request names its own recording (`ref_audio`): IndexTTS caches the
speaker conditioning of the last recording it was given, so a chapter in one
voice computes it once, and the voice sampler can read the same line in each
recording without reloading the model.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "text": ..., "output_path": ...,
                     "ref_audio": ..., "lang": "EN", "duration_factor": 1.0,
                     "interval_silence": 450, "seed": 0}
  Worker -> parent (once ready): {"event": "ready", "device": ...}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

Every model call runs with stdout redirected to a buffer so library prints
(IndexTTS prints a great deal) can't corrupt the protocol.
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
os.environ["HF_HUB_DISABLE_XET"] = "1"

real_stdout = sys.stdout
warnings.filterwarnings("ignore")

# One seed for every take unless a request names another: IndexTTS samples,
# so without one a re-run of a single take comes back as a different reading.
SEED = 0


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", required=True)
    args = parser.parse_args()
    model_dir = Path(args.model_dir).resolve()

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            # infer_v2_5 sets HF_HUB_CACHE to "./checkpoints/hf_cache" as it is
            # imported - relative to wherever we are. Standing in the model's
            # own folder keeps anything it caches there instead of in the repo.
            os.chdir(model_dir)
            import torch
            from indextts.infer_v2_5 import IndexTTS2

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            model = IndexTTS2(cfg_path=str(model_dir / "config.yaml"), model_dir=str(model_dir),
                              use_bf16=device.startswith("cuda"), device=device)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load IndexTTS-2.5: {e}"})
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
            output_path.unlink(missing_ok=True)

            with contextlib.redirect_stdout(io.StringIO()), torch.inference_mode():
                torch.manual_seed(int(req.get("seed", SEED)))
                model.infer(
                    spk_audio_prompt=req["ref_audio"], text=req["text"], output_path=str(output_path),
                    lang=req.get("lang") or "EN",
                    duration_factor=float(req.get("duration_factor", 1.0)),
                    interval_silence=int(req.get("interval_silence", 200)),
                )

            if not output_path.exists() or output_path.stat().st_size < 1000:
                raise RuntimeError("IndexTTS-2.5 produced no audio for this text")
            send({"ok": True})
        except Exception as e:
            # str() of a bare AssertionError is empty - fall back to the type.
            send({"ok": False, "error": str(e) or type(e).__name__})


if __name__ == "__main__":
    main()
