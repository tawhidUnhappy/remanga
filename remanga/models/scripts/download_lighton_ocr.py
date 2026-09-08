#!/usr/bin/env python3
"""Standalone LightOnOCR-2 weight downloader - runs inside the isolated
`.tools/venv-lighton-ocr` environment (that's where `huggingface_hub` lives;
see remanga/venvs.py). Zero dependency on the `remanga` package itself.

Usage: download_lighton_ocr.py <model_dir> <repo_id> [hf_token]
Exits 0 on success, non-zero with a message on stderr on failure - the caller
(remanga/models/weights.py) just needs the exit code.

Hugging Face Hub only, no ModelScope mirror: LightOn's models are published
on the Hub and a mirror that may not carry them is not a fallback, it is a
second way to fail slowly. Retries on outright failure (dropped connection
and the like) rather than racing two sources.

`hf_token` is optional (see remanga/hf_token.py); the repo is public, so it
is only needed on a Hub account that requires auth for everything.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
# Xet (HF's high-performance transfer) is genuinely faster when it works, but
# it has been observed hanging at 0 bytes indefinitely on large shards in this
# environment - process alive, no progress, no error, no timeout. Classic
# HTTP/LFS is slower and reliable, which is the right trade for a download
# that otherwise wedges a first-run bootstrap with no diagnostic.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

MAX_ATTEMPTS = 3


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: download_lighton_ocr.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir = Path(sys.argv[1]).resolve()
    repo_id = sys.argv[2]
    token = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3].strip() else None

    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        print(f"huggingface_hub is not installed in this environment: {e}", file=sys.stderr)
        return 1

    model_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(model_dir),
                # An IGNORE list, not an allow list. An allow list of
                # extensions silently drops anything it did not think of,
                # and it already did once: `chat_template.jinja` is not
                # .json/.safetensors/.txt/.model, so it was skipped, and the
                # model then loaded fine and failed on the first page with
                # "this processor does not have a chat template". Excluding
                # the few things that are definitely not needed is the safer
                # direction to be wrong in.
                ignore_patterns=["*.png", "*.jpg", "*.gif", ".eval_results/*", "*.pth", "*.bin"],
                token=token,
            )
            break
        except Exception as e:
            print(f">> attempt {attempt}/{MAX_ATTEMPTS} failed: {e}", file=sys.stderr)
            if attempt == MAX_ATTEMPTS:
                print(f"Failed to download {repo_id}.", file=sys.stderr)
                return 1
            time.sleep(min(5 * attempt, 30))

    config = model_dir / "config.json"
    weights = sorted(model_dir.glob("*.safetensors"))
    if not config.exists():
        print(f"Download finished but {config} is missing.", file=sys.stderr)
        return 1
    if not weights:
        print(f"Download finished but no .safetensors landed in {model_dir}.", file=sys.stderr)
        return 1

    total_mb = sum(w.stat().st_size for w in weights) / (1024 * 1024)
    print(f"LightOnOCR-2 ready: {len(weights)} safetensors file(s), {total_mb:.0f} MB in {model_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
