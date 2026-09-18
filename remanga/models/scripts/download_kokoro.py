#!/usr/bin/env python3
"""Standalone Kokoro-82M weight downloader - runs inside the isolated
`.tools/venv-kokoro` environment (that's where `huggingface_hub` lives; see
remanga/venvs.py). Zero dependency on the `remanga` package itself.

Usage: download_kokoro.py <model_dir> <repo_id> [hf_token]
Exits 0 on success, non-zero with a message on stderr on failure - the
caller (remanga/models/weights.py) just needs the exit code.

Pulls the weights, the model config and EVERY voice pack, not just the one
currently configured. The voices are a few hundred KB each against 327MB of
weights, and fetching them all here is what lets the worker run with no
network at all - otherwise changing the narrator in config.json would send
the next run back to the Hub mid-chapter, which is exactly where a download
should never happen.

`hf_token` is optional (see remanga/hf_token.py); Kokoro is a public repo,
so it is only needed on a Hub account that requires auth for everything.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: download_kokoro.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
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

    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(model_dir),
            allow_patterns=["config.json", "kokoro-v1_0.pth", "voices/*.pt"],
            token=token,
        )
    except Exception as e:
        print(f"Failed to download {repo_id}: {e}", file=sys.stderr)
        return 1

    weights = model_dir / "kokoro-v1_0.pth"
    voices = sorted((model_dir / "voices").glob("*.pt"))
    if not weights.exists() or weights.stat().st_size < 100_000:
        print(f"Download finished but {weights} is missing or truncated.", file=sys.stderr)
        return 1
    if not voices:
        print(f"Download finished but no voice packs landed in {model_dir / 'voices'}.", file=sys.stderr)
        return 1

    print(f"Kokoro-82M ready: {weights.name} + {len(voices)} voices in {model_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
