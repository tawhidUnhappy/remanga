#!/usr/bin/env python3
"""Standalone MAGI v3 weight downloader - runs inside the isolated `.venv-magi`
environment. Zero dependency on the `remanga` package itself.

Usage: download_magi.py <model_dir> <repo_id> [hf_token]

`hf_token` is optional (see remanga/hf_token.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

# _hash_verify.py's canonical copy lives under remanga/models/scripts/ - reused
# here via a plain sys.path insert (this script assumes zero dependency on the
# `remanga` package itself, same as its models/scripts/ siblings, so it can't
# import remanga.models.scripts either).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "models" / "scripts"))
from _hash_verify import delete_files_for_retry, verify_repo_files  # noqa: E402


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("Usage: download_magi.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir, repo_id = sys.argv[1], sys.argv[2]
    hf_token = sys.argv[3] if len(sys.argv) == 4 else None

    def _download() -> None:
        from huggingface_hub import snapshot_download
        # `cache_dir`, not `local_dir` - must match what magi_worker.py passes to
        # AutoModelForCausalLM.from_pretrained(cache_dir=...), or the two use
        # different on-disk layouts and the worker ends up re-downloading everything.
        snapshot_download(repo_id=repo_id, cache_dir=model_dir, token=hf_token)

    try:
        _download()
    except Exception as e:
        print(f"Error downloading MAGI v3 weights: {e}", file=sys.stderr)
        return 1

    print(f">> Downloaded MAGI v3 weights to {model_dir}")

    # See _hash_verify.py's docstring: snapshot_download's own check is
    # size-only. cache_layout=True since this uses cache_dir=, not local_dir=.
    ok, bad = verify_repo_files(model_dir, repo_id, hf_token, cache_layout=True)
    if not ok:
        print(f">> Re-fetching {len(bad)} corrupt file(s)...")
        delete_files_for_retry(model_dir, bad, cache_layout=True)
        try:
            _download()
        except Exception as e:
            print(f"Error re-downloading corrupt files: {e}", file=sys.stderr)
            return 1
        ok, bad = verify_repo_files(model_dir, repo_id, hf_token, cache_layout=True)
        if not ok:
            print(f"Error: {len(bad)} file(s) still fail hash verification after retry: {', '.join(bad)}",
                  file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
