#!/usr/bin/env python3
"""Standalone IndexTTS-2.5 weight downloader - runs inside the isolated
`.venv-indextts` environment (that's where `modelscope`/`huggingface_hub` now
live; see remanga/venvs.py). Zero dependency on the `remanga` package itself.

Usage: download_indextts.py <model_dir> <repo_id> [hf_token]
Tries the ModelScope CDN mirror first (usually much faster), falls back to
the Hugging Face Hub. Exits 0 on success, non-zero with a message on stderr
on failure - the caller (remanga/models/weights.py) just needs the exit code.

`hf_token` is optional (see remanga/hf_token.py) - only used for the HF Hub
fallback, never ModelScope (a different service, different token scheme -
passing an HF token there wouldn't do anything useful).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hash_verify import delete_files_for_retry, verify_repo_files  # noqa: E402

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
os.environ.setdefault("MODELSCOPE_LOG_LEVEL", "40")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("Usage: download_indextts.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir, repo_id = sys.argv[1], sys.argv[2]
    hf_token = sys.argv[3] if len(sys.argv) == 4 else None

    downloaded_via = None
    try:
        from modelscope import snapshot_download as ms_download
        ms_download(model_id=repo_id, local_dir=model_dir)
        downloaded_via = "ModelScope mirror"
    except Exception as e:
        print(f">> ModelScope mirror failed ({e}), falling back to Hugging Face Hub...", file=sys.stderr)

    def _hf_download() -> None:
        from huggingface_hub import snapshot_download as hf_download
        hf_download(
            repo_id=repo_id,
            local_dir=model_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
            max_retries=10,
            token=hf_token,
        )

    if downloaded_via is None:
        try:
            _hf_download()
            downloaded_via = "Hugging Face Hub"
        except Exception as e:
            print(f"Error downloading model weights: {e}", file=sys.stderr)
            return 1

    print(f">> Downloaded via {downloaded_via} to {model_dir}")

    # Verified against the Hub's own recorded sha256 regardless of which
    # mirror actually served the bytes - see _hash_verify.py's docstring for
    # why snapshot_download's own size check alone isn't enough. One retry:
    # delete just the corrupt files and re-fetch through the Hub directly
    # (ModelScope may be the one that produced them, so don't retry there).
    ok, bad = verify_repo_files(model_dir, repo_id, hf_token, cache_layout=False)
    if not ok:
        print(f">> Re-fetching {len(bad)} corrupt file(s) via Hugging Face Hub...")
        delete_files_for_retry(model_dir, bad, cache_layout=False)
        try:
            _hf_download()
        except Exception as e:
            print(f"Error re-downloading corrupt files: {e}", file=sys.stderr)
            return 1
        ok, bad = verify_repo_files(model_dir, repo_id, hf_token, cache_layout=False)
        if not ok:
            print(f"Error: {len(bad)} file(s) still fail hash verification after retry: {', '.join(bad)}",
                  file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
