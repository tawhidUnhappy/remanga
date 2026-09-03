#!/usr/bin/env python3
"""Standalone MAGI v3 weight downloader - runs inside the isolated `.venv-magi`
environment. Zero dependency on the `remanga` package itself.

Usage: download_magi.py <model_dir> <repo_id> [hf_token]

`hf_token` is optional (see remanga/hf_token.py).
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("Usage: download_magi.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir, repo_id = sys.argv[1], sys.argv[2]
    hf_token = sys.argv[3] if len(sys.argv) == 4 else None
    try:
        from huggingface_hub import snapshot_download
        # `cache_dir`, not `local_dir` - must match what magi_worker.py passes to
        # AutoModelForCausalLM.from_pretrained(cache_dir=...), or the two use
        # different on-disk layouts and the worker ends up re-downloading everything.
        snapshot_download(repo_id=repo_id, cache_dir=model_dir, token=hf_token)
        print(f">> Downloaded MAGI v3 weights to {model_dir}")
        return 0
    except Exception as e:
        print(f"Error downloading MAGI v3 weights: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
