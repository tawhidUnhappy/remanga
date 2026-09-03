#!/usr/bin/env python3
"""Standalone DeepSeek-OCR-2 recognition worker - runs inside the isolated
`.venv-deepseek-ocr` environment as a long-lived subprocess, spoken to by
remanga/ocr/engine.py (in the main env) over the same line-delimited JSON
protocol remanga/audio/scripts/{indextts,audio8}_worker.py use. Deliberately
has ZERO dependency on the `remanga` package itself - only
`transformers`/`torch`/`PIL` and the stdlib - so it works regardless of
what's importable in the caller's environment. One persistent process per
Narration Writer session, so the model loads onto the GPU once, not once per
"OCR this panel" click.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "recognize", "image_path": "...", "prompt": "..."}
  Worker -> parent (once ready): {"event": "ready"} or {"event": "error", "error": "..."}
  Worker -> parent (per request): {"ok": true, "text": "..."} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

GPU preferred whenever available (torch.cuda.is_available()), CPU fallback
otherwise - OCR is CPU-viable but far slower, so this always prefers CUDA
the same way audio8_worker.py's own device selection does.

Loaded with trust_remote_code=True (DeepSeek-OCR ships its own custom
modeling code - see its model card). DeepSeek-OCR-2's exact API wasn't
reachable to verify while writing this (see the remanga-ops skill's DeepSeek-
OCR-2 section) - `.infer(tokenizer, prompt=, image_file=, ...)` is what
DeepSeek-OCR (v1)'s published model card documents, the most likely
interface for a same-org follow-up release to keep. If `.infer()` doesn't
return the recognized text directly, this also falls back to reading
whatever text-like file it saved into a scratch output directory (documented
behavior for save_results=True on the v1 model). Adjust here once the real
v2 interface is confirmed.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

real_stdout = sys.stdout

DEFAULT_PROMPT = "<image>\nFree OCR."


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def main() -> None:
    if len(sys.argv) != 2:
        send({"event": "error", "error": "Usage: deepseek_ocr_worker.py <model_dir>"})
        sys.exit(2)
    model_dir = sys.argv[1]

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"

        with contextlib.redirect_stdout(io.StringIO()):
            tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
            model = AutoModel.from_pretrained(
                model_dir, trust_remote_code=True, use_safetensors=True,
            ).eval().to(device)
            if device == "cuda":
                model = model.to(torch.bfloat16)
    except Exception as e:
        send({"event": "error", "error": f"Failed to load DeepSeek-OCR-2: {e}"})
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
            image_path = req["image_path"]
            prompt = req.get("prompt") or DEFAULT_PROMPT

            with tempfile.TemporaryDirectory() as out_dir, contextlib.redirect_stdout(io.StringIO()):
                result = model.infer(
                    tokenizer,
                    prompt=prompt,
                    image_file=image_path,
                    output_path=out_dir,
                    base_size=1024,
                    image_size=640,
                    crop_mode=True,
                    save_results=True,
                )
                text = result.strip() if isinstance(result, str) else ""
                if not text:
                    candidates = sorted(Path(out_dir).glob("*.md")) + sorted(Path(out_dir).glob("*.mmd")) \
                        + sorted(Path(out_dir).glob("*.txt"))
                    if candidates:
                        text = candidates[0].read_text(encoding="utf-8", errors="replace").strip()

            send({"ok": True, "text": text})
        except Exception as e:
            send({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
