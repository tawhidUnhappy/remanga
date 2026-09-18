#!/usr/bin/env python3
"""Standalone Qwen3-TTS weight downloader - runs inside the isolated
`.tools/venv-qwen-tts` environment (that's where `huggingface_hub` lives; see
remanga/tool_envs/). Zero dependency on the `remanga` package itself.

Usage: download_qwen_tts.py <model_dir> <repo_id> [hf_token]
Exits 0 on success, non-zero with a message on stderr on failure - the caller
(remanga/models/weights.py) just needs the exit code.

One variant per call: which one is decided by the repo_id the caller passes
(see audio/synth/qwen.py:VARIANTS), so only the models a chapter actually
needs are ever fetched - a preset narrator never downloads the design model.

Xet is disabled and each attempt is a plain retry: Xet transfers have hung at
0 bytes on this project before - no error, no timeout, no progress - while
classic HTTP is slower and finishes. `hf_token` is optional (see
remanga/hf_token.py); these repos are public and ungated.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Read by huggingface_hub when it is imported, so set before that happens.
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# The model, its config and its tokenizer - not the repo's samples or cards.
ALLOW_PATTERNS = ["*.safetensors", "*.safetensors.index.json", "*.json", "*.txt", "*.model", "*.yaml"]
REQUIRED_FILES = ("config.json",)
MAX_ATTEMPTS = 3


def _download(repo_id: str, model_dir: Path, token: str | None) -> bool:
    from huggingface_hub import snapshot_download

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            snapshot_download(repo_id=repo_id, local_dir=str(model_dir),
                              allow_patterns=ALLOW_PATTERNS, token=token)
            return True
        except Exception as e:
            print(f">> Download attempt {attempt}/{MAX_ATTEMPTS} failed: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                time.sleep(5 * attempt)
    return False


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: download_qwen_tts.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir = Path(sys.argv[1]).resolve()
    repo_id = sys.argv[2]
    token = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3].strip() else None

    model_dir.mkdir(parents=True, exist_ok=True)
    if not _download(repo_id, model_dir, token):
        print(f"Failed to download {repo_id}.", file=sys.stderr)
        return 1

    missing = [name for name in REQUIRED_FILES if not (model_dir / name).is_file()]
    weights = list(model_dir.glob("*.safetensors"))
    if missing or not weights:
        print(f"Download finished but {', '.join(missing) or 'the weights'} did not land in {model_dir}.",
              file=sys.stderr)
        return 1

    print(f"{repo_id} ready in {model_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
