#!/usr/bin/env python3
"""Standalone Ming-3.0-tts weight downloader - runs inside the isolated
`.tools/venv-ming-tts` environment. Zero dependency on the `remanga` package.

Usage: download_ming_tts.py <model_dir> <repo_id> [hf_token]
Exits 0 on success, non-zero with a message on stderr on failure.

Fetches what MingTTS loads - the checkpoint, its configs and tokenizer, and
campplus.onnx (the speaker-embedding model it builds at load time even when
no recording is used) - and skips the repo's figures and paper."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# run.sh turns hf_transfer on, but this environment doesn't have it, and
# huggingface_hub refuses to download at all when it is asked for and missing.
if importlib.util.find_spec("hf_transfer") is None:
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: download_ming_tts.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
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
            allow_patterns=["*.json", "*.txt", "*.jinja", "*.safetensors", "*.onnx"],
            token=token,
        )
    except Exception as e:
        print(f"Failed to download {repo_id}: {e}", file=sys.stderr)
        return 1

    for name in ("model.safetensors", "campplus.onnx", "tokenizer.json", "config.json"):
        path = model_dir / name
        if not path.exists() or path.stat().st_size < 1_000:
            print(f"Download finished but {path} is missing or truncated.", file=sys.stderr)
            return 1

    print(f"Ming-3.0-tts ready in {model_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
