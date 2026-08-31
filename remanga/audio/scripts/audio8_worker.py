#!/usr/bin/env python3
"""Standalone Audio8-TTS-Preview-0.1b synthesis worker - runs inside the
isolated `.venv-audio8` environment as a long-lived subprocess, spoken to by
remanga/audio/synth.py (in the main env) over the same line-delimited JSON
protocol indextts_worker.py uses. Deliberately has ZERO dependency on the
`remanga` package itself - only `transformers`/`torch`/`soundfile` and the
stdlib - so it works regardless of what's importable in the caller's
environment. See indextts_worker.py's module docstring for the shared
reasoning behind this whole worker-process design (one persistent process
per production run, so the model loads onto the GPU once, not once per
panel).

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "spk_audio_prompt": ..., "text": ...,
                     "reference_text": ..., "output_path": ..., "temperature": ...,
                     "top_p": ..., "max_new_tokens": ...}
  Worker -> parent (once ready): {"event": "ready"}
  Worker -> parent (per request): {"ok": true} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

Loaded with trust_remote_code=True (Audio8/Audio8-TTS-Preview-0.1b ships its
own custom `modeling_arktts*.py`/`processing_arktts.py` - see its model
card); everything the model/processor print unconditionally during
load/inference is redirected away from stdout the same way indextts_worker.py
does, so it can never corrupt this protocol.
"""

from __future__ import annotations

import argparse
import contextlib
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
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--use_bf16", action="store_true")
    args = parser.parse_args()

    try:
        import torch
        from transformers import AutoModel, AutoProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if (args.use_bf16 and device == "cuda") else None

        with contextlib.redirect_stdout(io.StringIO()):
            processor = AutoProcessor.from_pretrained(args.model_dir, trust_remote_code=True)
            model_kwargs = {"trust_remote_code": True}
            if dtype is not None:
                model_kwargs["dtype"] = dtype
            model = AutoModel.from_pretrained(args.model_dir, **model_kwargs).eval().to(device)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load Audio8 TTS: {e}"})
        sys.exit(1)

    send({"event": "ready"})

    import soundfile as sf

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
                "text": [req["text"]],
                "return_tensors": "pt",
            }
            spk_prompt = req.get("spk_audio_prompt")
            if spk_prompt:
                call_kwargs["reference_audio"] = [spk_prompt]
                # This engine's cloning quality depends on an accurate
                # transcript of the reference audio, unlike IndexTTS-2.5's
                # audio-only zero-shot cloning - see Audio8Config.reference_text.
                call_kwargs["reference_text"] = [req.get("reference_text") or ""]

            with contextlib.redirect_stdout(io.StringIO()):
                inputs = processor(**call_kwargs)
                inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}

                gen_kwargs = {
                    "max_new_tokens": req.get("max_new_tokens", 512),
                    "temperature": req.get("temperature", 0.7),
                    "top_p": req.get("top_p", 0.9),
                    "do_sample": True,
                }
                output = model.generate(**inputs, **gen_kwargs)
                waveforms, lengths = model.decode_audio(output.codes)

            wav = waveforms[0]
            length = int(lengths[0]) if lengths is not None else wav.shape[-1]
            wav = wav[..., :length]
            wav_np = wav.detach().to("cpu").float().numpy()
            if wav_np.ndim > 1:
                wav_np = wav_np.squeeze()

            sample_rate = getattr(getattr(model, "config", None), "sampling_rate", None) or 44100
            output_path = req["output_path"]
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            sf.write(output_path, wav_np, sample_rate)

            if not Path(output_path).exists():
                raise RuntimeError("generate()/decode_audio() completed but no output file was written")

            send({"ok": True})
        except Exception as e:
            send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
