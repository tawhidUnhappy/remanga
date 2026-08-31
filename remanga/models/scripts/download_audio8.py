#!/usr/bin/env python3
"""Standalone Audio8-TTS-Preview-0.1b weight downloader - runs inside the
isolated `.venv-audio8` environment (that's where `huggingface_hub` lives;
see remanga/venvs.py). Zero dependency on the `remanga` package itself -
mirrors remanga/models/scripts/download_indextts.py's shape exactly, minus
the ModelScope-mirror-first step (Audio8 isn't mirrored there).

Usage: download_audio8.py <model_dir> <repo_id>
Exits 0 on success, non-zero with a message on stderr on failure - the
caller (remanga/models/weights.py) just needs the exit code.
"""

from __future__ import annotations

import logging
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

# This huggingface_hub version's snapshot_download() dropped the max_retries
# kwarg older versions had, so flaky-connection retries (e.g. a dropped
# connection partway through a large file) are handled by hand here instead.
# snapshot_download() itself already skips/resumes files already on disk in
# `local_dir`, so a retry after a partial failure only re-fetches what's
# actually missing or incomplete - not the whole snapshot.
MAX_ATTEMPTS = 5


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: download_audio8.py <model_dir> <repo_id>", file=sys.stderr)
        return 2

    model_dir, repo_id = sys.argv[1], sys.argv[2]

    from huggingface_hub import snapshot_download as hf_download

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            hf_download(
                repo_id=repo_id,
                local_dir=model_dir,
            )
            print(f">> Downloaded via Hugging Face Hub to {model_dir}")
            return 0
        except Exception as e:
            last_error = e
            print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(5 * attempt, 30))

    print(f"Error downloading model weights: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
