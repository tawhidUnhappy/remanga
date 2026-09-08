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
  Parent -> worker: {"cmd": "recognize", "image_path": "...", "prompt": "...",
                     "base_size": N, "image_size": N, "crop_mode": bool}
  Worker -> parent (once ready): {"event": "ready"} or {"event": "error", "error": "..."}
  Worker -> parent (per request): {"ok": true, "text": "..."} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

GPU preferred whenever available (torch.cuda.is_available()), CPU fallback
otherwise - OCR is CPU-viable but far slower, so this always prefers CUDA
the same way audio8_worker.py's own device selection does.

Loaded with trust_remote_code=True (DeepSeek-OCR-2 ships its own custom
modeling code - see its model card). The `.infer(tokenizer, prompt=,
image_file=, output_path=, base_size=, image_size=, crop_mode=,
save_results=)` call below IS the published v2 interface, confirmed against
the model card - an earlier version of this file guessed it from v1 and said
so; the guess turned out right, but `image_size` is 768 in the real card, not
the 640 that guess used.

`.infer()` writes its results into `output_path`, and what it returns
directly is not guaranteed to be the text, so this reads the saved file when
the return value isn't usable. That fallback is kept deliberately: it is the
documented behavior of save_results=True, and it costs nothing when the
return value is fine.

flash_attention_2 is NOT requested even though the model card uses it.
flash-attn is a compiled CUDA extension with a long, fragile build and it is
not needed for correctness - transformers falls back to its own attention
implementation. Bootstrap already refuses to make a first run wait on an
optional kernel build; the same reasoning applies here.
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


def _available_ram_gb() -> float:
    """Free system RAM in GB, from /proc/meminfo's MemAvailable.

    Read straight out of /proc rather than through psutil: this worker is
    meant to need nothing but transformers and the stdlib, and a memory check
    that itself depends on an extra package is a check that silently does not
    run on the machine that needed it most."""
    try:
        with Path("/proc/meminfo").open() as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except Exception:
        pass
    return -1.0  # unknown - do not block on a number we could not read


# Loading ~3B parameters at bfloat16 needs roughly this much RAM in transit,
# even with low_cpu_mem_usage streaming the shards. Deliberately a floor, not
# a precise figure: the point is to fail with a sentence someone can act on
# instead of letting the kernel OOM killer choose a victim, which on a
# desktop is frequently the desktop.
_MIN_LOAD_RAM_GB = 8.0


def _insufficient_ram() -> str:
    available = _available_ram_gb()
    if available < 0 or available >= _MIN_LOAD_RAM_GB:
        return ""
    return (
        f"Not enough free system RAM to load DeepSeek-OCR-2: {available:.1f}GB available, "
        f"~{_MIN_LOAD_RAM_GB:.0f}GB needed to stage a 3B-parameter checkpoint. "
        f"This check exists because loading it without one once triggered the kernel "
        f"OOM killer. Close some applications and retry."
    )


def main() -> None:
    if len(sys.argv) != 2:
        send({"event": "error", "error": "Usage: deepseek_ocr_worker.py <model_dir>"})
        sys.exit(2)
    model_dir = sys.argv[1]

    # Checked BEFORE importing torch: the failure this prevents is a
    # machine-wide OOM, and by the time the weights are being staged there is
    # no graceful way back out of it.
    headroom_error = _insufficient_ram()
    if headroom_error:
        send({"event": "error", "error": headroom_error})
        sys.exit(1)

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"

        with contextlib.redirect_stdout(io.StringIO()):
            tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
            # dtype and low_cpu_mem_usage are BOTH load-time arguments, and
            # both have to be: this model is ~3B parameters, and the model
            # card's own `.from_pretrained(...).cuda().to(torch.bfloat16)`
            # casts far too late. Without a dtype, transformers materializes
            # every parameter in float32 in SYSTEM RAM first - 3B x 4 bytes =
            # ~12GB - and only then moves and casts. On a 14GB machine that
            # invoked the kernel OOM killer and took the desktop down with it
            # (measured: anon-rss 11,967,492kB at the kill). The GPU was never
            # the constraint and never even got reached.
            #
            # Asking for bfloat16 up front halves that to ~6.8GB, and
            # low_cpu_mem_usage streams the checkpoint shard by shard instead
            # of building a second full copy alongside the first.
            dtype = torch.bfloat16 if device == "cuda" else torch.float32
            model = AutoModel.from_pretrained(
                model_dir, trust_remote_code=True, use_safetensors=True,
                torch_dtype=dtype, low_cpu_mem_usage=True,
            ).eval().to(device)
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
                    base_size=int(req.get("base_size", 1024)),
                    image_size=int(req.get("image_size", 768)),
                    crop_mode=bool(req.get("crop_mode", True)),
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
