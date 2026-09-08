#!/usr/bin/env python3
"""Standalone LightOnOCR-2 recognition worker - runs inside the isolated
`.venv-lighton-ocr` environment as a long-lived subprocess, spoken to by
remanga/ocr/engine.py (in the main env) over the same line-delimited JSON
protocol remanga/audio/scripts/kokoro_worker.py uses. Deliberately has ZERO
dependency on the `remanga` package itself - only
`transformers`/`torch`/`PIL` and the stdlib - so it works regardless of what's
importable in the caller's environment. One persistent process per Narration
Writer session, so the model loads onto the GPU once, not once per "OCR this
panel" click.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "recognize", "image_path": "...", "prompt": "...",
                     "max_new_tokens": N}
  Worker -> parent (once ready): {"event": "ready"} or {"event": "error", "error": "..."}
  Worker -> parent (per request): {"ok": true, "text": "..."} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

GPU preferred whenever available (torch.cuda.is_available()), CPU fallback
otherwise - OCR is CPU-viable but far slower, so this always prefers CUDA the
same way kokoro_worker.py's own device selection does. bfloat16 on CUDA,
float32 elsewhere: LightOnOCR-2's own card uses float32 on MPS because
bfloat16 is not reliably supported there, and the same caution applies to CPU.

No trust_remote_code: LightOnOCR-2 is supported natively in transformers
(>=5.0), so the model and processor classes are imported directly. That is a
real difference from the DeepSeek-OCR-2 worker this replaced, which loaded
custom remote modeling code and guessed at an `.infer()` signature that was
never verified against the actual release.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import warnings

real_stdout = sys.stdout
warnings.filterwarnings("ignore")


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    if len(sys.argv) != 2:
        send({"event": "error", "error": "Usage: lighton_ocr_worker.py <model_dir>"})
        sys.exit(2)
    model_dir = sys.argv[1]

    try:
        import torch
        from transformers import LightOnOcrForConditionalGeneration, LightOnOcrProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32

        with contextlib.redirect_stdout(io.StringIO()):
            model = LightOnOcrForConditionalGeneration.from_pretrained(
                model_dir, dtype=dtype,
            ).to(device).eval()
            processor = LightOnOcrProcessor.from_pretrained(model_dir)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load LightOnOCR-2: {e}"})
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
            # An image and nothing else is the plain "parse this page" case,
            # which is what a manga panel wants; a prompt is only added when
            # the caller actually sent one, since an empty text turn is not
            # the same thing as no text turn to the chat template.
            content: list[dict] = [{"type": "image", "path": req["image_path"]}]
            prompt = (req.get("prompt") or "").strip()
            if prompt:
                content.append({"type": "text", "text": prompt})

            with contextlib.redirect_stdout(io.StringIO()):
                inputs = processor.apply_chat_template(
                    [{"role": "user", "content": content}],
                    add_generation_prompt=True, tokenize=True,
                    return_dict=True, return_tensors="pt",
                )
                inputs = {
                    k: (v.to(device=device, dtype=dtype) if hasattr(v, "is_floating_point")
                        and v.is_floating_point() else v.to(device))
                    for k, v in inputs.items()
                }
                output_ids = model.generate(
                    **inputs, max_new_tokens=int(req.get("max_new_tokens", 512)),
                )
                # Slice off the prompt: generate() returns it prepended, and
                # decoding the whole thing would hand the UI the chat
                # template's own scaffolding as if the model had read it off
                # the panel.
                generated = output_ids[0, inputs["input_ids"].shape[1]:]
                text = processor.decode(generated, skip_special_tokens=True).strip()

            send({"ok": True, "text": text})
        except Exception as e:
            send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
