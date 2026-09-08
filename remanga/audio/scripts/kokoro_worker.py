#!/usr/bin/env python3
"""Standalone Kokoro-82M synthesis worker - runs inside the isolated
`.tools/venv-kokoro` environment as a long-lived subprocess, spoken to by
remanga/audio/synth/ (in the main env) over a line-delimited JSON protocol
on stdin/stdout. Deliberately has ZERO dependency on the `remanga` package
itself - only `kokoro` and the stdlib - so it works regardless of what's
importable in the caller's environment.

Why a persistent worker when Kokoro is small enough to load quickly: the
model is the cheap part, but `KPipeline` also builds misaki's English G2P,
which loads a spaCy pipeline - and that, not the 82M of weights, is what
makes per-process startup hurt across a 100+ panel chapter. This process is
spawned once per `remanga tts` run and handles every panel in that run.

Everything is loaded from `--model_dir` rather than fetched at synthesis
time: the weights, the config and the voice packs all come off disk (the
download script put them there), so a chapter never stalls on a Hub round
trip and a machine with no network still synthesizes. Kokoro's own voice
loader takes a path when the name ends in `.pt`, which is how the voice is
handed over without it reaching for huggingface_hub.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "voice": ..., "text": ...,
                     "output_path": ..., "speed": ...}
  `voice` is one of Kokoro's built-in voice names (see
  remanga/config/kokoro_voices.py) - there is no reference clip and no
  cloning. It is sent per request rather than fixed at spawn because
  Kokoro loads voices lazily and cheaply, so one worker can serve several.
  Worker -> parent (once ready): {"event": "ready"}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

KPipeline and its dependencies print and warn to stdout on import and on
first use; those would corrupt this protocol if left alone, so every model
call happens with stdout redirected to a buffer. Only this script's own
explicit protocol writes (via the `real_stdout` handle captured before any
redirect) reach the parent.
"""

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
    parser.add_argument("--lang_code", default="a")
    parser.add_argument("--repo_id", default="hexgrad/Kokoro-82M")
    parser.add_argument("--sample_rate", type=int, default=24000)
    args = parser.parse_args()

    model_dir = Path(args.model_dir)

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import numpy as np
            import soundfile as sf
            import torch
            from kokoro import KModel, KPipeline

            device = "cuda" if torch.cuda.is_available() else "cpu"
            kmodel = KModel(
                repo_id=args.repo_id,
                config=str(model_dir / "config.json"),
                model=str(model_dir / "kokoro-v1_0.pth"),
            ).to(device).eval()
            pipeline = KPipeline(
                lang_code=args.lang_code, repo_id=args.repo_id, model=kmodel, device=device,
            )
    except Exception as e:
        send({"event": "error", "error": f"Failed to load Kokoro: {e}"})
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

            # KPipeline yields one result per chunk it decides to split the
            # text into, so a panel can come back as several arrays; they are
            # concatenated into the single WAV the rest of the pipeline
            # expects. Torch tensors and numpy arrays both turn up here
            # depending on version, hence the detach/asarray dance.
            # Kokoro's loader treats a name ending in ".pt" as a path and
            # skips the Hub entirely; anything else it would try to download.
            voice_pack = model_dir / "voices" / f"{req['voice']}.pt"
            voice = str(voice_pack) if voice_pack.exists() else req["voice"]

            chunks: list = []
            with contextlib.redirect_stdout(io.StringIO()):
                for _, _, audio in pipeline(
                    req["text"], voice=voice, speed=float(req.get("speed", 1.0)),
                ):
                    if audio is None:
                        continue
                    arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
                    chunks.append(arr.astype("float32").reshape(-1))

            if not chunks:
                raise RuntimeError("Kokoro produced no audio for this text")

            sf.write(str(output_path), np.concatenate(chunks), args.sample_rate)

            if not output_path.exists():
                raise RuntimeError("synthesis returned without writing an output file")

            send({"ok": True})
        except Exception as e:
            send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
