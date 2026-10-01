#!/usr/bin/env python3
"""Standalone faster-whisper weight downloader - runs inside the isolated
`.tools/venv-faster-whisper` environment (that's where `huggingface_hub`
lives; see remanga/tool_envs/). Zero dependency on the `remanga` package.

Usage: download_whisper.py <model_dir> <repo_id> [hf_token]
Exits 0 on success, non-zero with a message on stderr on failure - the caller
(remanga/models/weights.py) just needs the exit code.

Fetched to checkpoints/ rather than left to faster-whisper's own by-name
download for the same reason every other model here is: a chapter should
never stall on a Hub round trip, and a machine with no network should still
be able to read its timings back.

CTranslate2 weights, so `model.bin` rather than safetensors, plus the
tokenizer and the converter's config.

Xet is disabled and each attempt is a plain retry: Xet transfers have hung at
0 bytes on this project before - no error, no timeout, no progress - while
classic HTTP is slower and finishes. `hf_token` is optional (see
remanga/hf_token.py); this repo is public and ungated.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Read by huggingface_hub when it is imported, so set before that happens.
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

ALLOW_PATTERNS = ["*.bin", "*.json", "*.txt"]
REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json")
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
        print("usage: download_whisper.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir = Path(sys.argv[1]).resolve()
    repo_id = sys.argv[2]
    token = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3].strip() else None

    model_dir.mkdir(parents=True, exist_ok=True)
    if not _download(repo_id, model_dir, token):
        print(f"Failed to download {repo_id}.", file=sys.stderr)
        return 1

    missing = [name for name in REQUIRED_FILES if not (model_dir / name).is_file()]
    if missing:
        print(f"Download finished but {', '.join(missing)} did not land in {model_dir}.", file=sys.stderr)
        return 1

    print(f"{repo_id} ready in {model_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
