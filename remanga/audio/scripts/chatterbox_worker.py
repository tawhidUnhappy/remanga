#!/usr/bin/env python3
"""Standalone Chatterbox Turbo synthesis worker - runs inside the isolated
`.tools/venv-chatterbox` environment as a long-lived subprocess, spoken to by
remanga/audio/synth/chatterbox.py (in the main env) over a line-delimited
JSON protocol on stdin/stdout. Deliberately has ZERO dependency on the
`remanga` package itself - only `chatterbox-tts` and the stdlib - for the same
reason kokoro_worker.py doesn't.

Chatterbox Turbo (ResembleAI/chatterbox-turbo, 350M, MIT) clones a narrator
from a reference recording instead of shipping named voices, so where
Kokoro's requests carry a voice NAME these carry a clip PATH. Turning that
clip into what the model conditions on - a speaker embedding plus speech
tokens from its first 15 seconds - is real work, so it happens once per clip
rather than once per panel: the conditionals are kept, and rebuilt only when
a request names a different file, or the same file after it changed on disk.

Every panel is generated from the same fixed seed. Turbo samples
(temperature 0.8), so without one, re-running a panel - which resume does to
the panels either side of an interruption - comes back as a different take
of the line than the takes around it.

Everything loads from `--model_dir` via `from_local`, never `from_pretrained`:
download_chatterbox.py put the weights there, and a chapter should never
stall on a Hub round trip.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "reference_audio": ..., "text": ...,
                     "output_path": ...}
  Worker -> parent (once ready): {"event": "ready", "device": ...}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

There is no speed field: Turbo has no speaking-rate control, so the parent
time-stretches the finished clip instead (see ChatterboxSynthesizer).

As in kokoro_worker.py, every model call runs with stdout redirected to a
buffer so library prints can't corrupt the protocol. TQDM_DISABLE is set
before anything imports tqdm: Turbo draws a progress bar on stderr for every
generation, and the parent keeps stderr's last lines for its error messages -
a real failure would otherwise be reported as a screen of progress-bar
redraws.
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

# One seed for every panel - see the module docstring.
SEED = 0


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", required=True)
    args = parser.parse_args()

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import soundfile as sf
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
            model = ChatterboxTurboTTS.from_local(Path(args.model_dir), device)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load Chatterbox Turbo: {e}"})
        sys.exit(1)

    send({"event": "ready", "device": device})

    # (resolved path, size, mtime) of the clip model.conds was last built
    # from, so editing the clip in place is noticed without a restart.
    conditioned_on: tuple | None = None

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

            reference = Path(req["reference_audio"])
            stat = reference.stat()
            clip_key = (str(reference.resolve()), stat.st_size, stat.st_mtime_ns)

            # inference_mode: upstream decorates sampling and decoding with
            # it, but not s3gen.embed_ref, which prepare_conditionals calls
            # for every new clip.
            with contextlib.redirect_stdout(io.StringIO()), torch.inference_mode():
                if clip_key != conditioned_on:
                    conditioned_on = None
                    model.prepare_conditionals(str(reference))
                    conditioned_on = clip_key
                torch.manual_seed(SEED)
                wav = model.generate(req["text"])

            audio = wav.squeeze(0).detach().cpu().numpy().astype("float32")
            if audio.size == 0:
                raise RuntimeError("Chatterbox produced no audio for this text")

            sf.write(str(output_path), audio, model.sr)

            if not output_path.exists():
                raise RuntimeError("synthesis returned without writing an output file")

            send({"ok": True})
        except Exception as e:
            # str() of a bare AssertionError is empty - upstream asserts on
            # a too-short reference clip - so fall back to the type name.
            send({"ok": False, "error": str(e) or type(e).__name__})


if __name__ == "__main__":
    main()
