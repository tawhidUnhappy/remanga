#!/usr/bin/env python3
"""Standalone Qwen3-TTS synthesis worker - runs inside the isolated
`.tools/venv-qwen-tts` environment as a long-lived subprocess, spoken to by
remanga/audio/synth/qwen.py (in the main env) over a line-delimited JSON
protocol on stdin/stdout. Deliberately has ZERO dependency on the `remanga`
package itself - only `qwen-tts` and the stdlib - for the same reason
kokoro_worker.py doesn't.

`--mode` picks which of Qwen3-TTS's three ways this worker is for, because
each is a different checkpoint (`--model_dir`):

  custom  a preset narrator (`speaker`), optionally steered by `instruct`
  clone   the voice in `--ref_audio` - remanga uses it to speak every panel
          in a designed voice's own sample, so a chapter is one voice. The
          clone prompt is built once, here, not per request: rebuilding it
          per panel is both slower and what makes the voice wander.
  design  one sample of the voice an `instruct` description asks for. Used
          once from the settings screen, then closed.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "text": ..., "output_path": ...,
                     "speaker": ..., "instruct": ...}
  Worker -> parent (once ready): {"event": "ready", "device": ...}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
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

# One seed for every panel: Qwen3-TTS samples, so without one a re-run of a
# single panel - which resume does around an interruption - comes back as a
# different take than the panels either side of it.
SEED = 0


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--mode", required=True, choices=("custom", "clone", "design"))
    parser.add_argument("--language", default="English")
    parser.add_argument("--ref_audio", default="")
    parser.add_argument("--ref_text", default="")
    args = parser.parse_args()

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import soundfile as sf
            import torch
            from qwen_tts import Qwen3TTSModel

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            model = Qwen3TTSModel.from_pretrained(
                args.model_dir, device_map=device,
                dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32,
            )
            clone_prompt = None
            if args.mode == "clone":
                clone_prompt = model.create_voice_clone_prompt(
                    ref_audio=args.ref_audio, ref_text=args.ref_text or None,
                )
    except Exception as e:
        send({"event": "error", "error": f"Failed to load Qwen3-TTS: {e}"})
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
            text = req["text"]

            with contextlib.redirect_stdout(io.StringIO()), torch.inference_mode():
                torch.manual_seed(SEED)
                if args.mode == "custom":
                    wavs, sr = model.generate_custom_voice(
                        text=text, speaker=req.get("speaker") or "Ryan", language=args.language,
                        instruct=req.get("instruct") or None,
                    )
                elif args.mode == "clone":
                    wavs, sr = model.generate_voice_clone(
                        text=text, language=args.language, voice_clone_prompt=clone_prompt,
                        non_streaming_mode=True,
                    )
                else:
                    wavs, sr = model.generate_voice_design(
                        text=text, instruct=req.get("instruct") or "", language=args.language,
                    )

            audio = wavs[0]
            if audio is None or len(audio) == 0:
                raise RuntimeError("Qwen3-TTS produced no audio for this text")
            sf.write(str(output_path), audio, sr)

            if not output_path.exists():
                raise RuntimeError("synthesis returned without writing an output file")

            send({"ok": True})
        except Exception as e:
            # str() of a bare AssertionError is empty - fall back to the type.
            send({"ok": False, "error": str(e) or type(e).__name__})


if __name__ == "__main__":
    main()
