#!/usr/bin/env python3
"""Standalone DeepSeek-OCR-2 weight downloader - runs inside the isolated
`.venv-deepseek-ocr` environment (that's where `modelscope`/`huggingface_hub`
live; see remanga/venvs.py). Zero dependency on the `remanga` package itself.

Usage: download_deepseek_ocr.py <model_dir> <repo_id>

Tries the Hugging Face Hub first (classic HTTP/LFS transfer, Xet explicitly
disabled - see below), falls back to the ModelScope mirror if that fails.
Opposite priority from download_indextts.py (ModelScope first) - see the
remanga-ops skill's DeepSeek-OCR-2 section for why (a real run saw
ModelScope's mirror stall for over an hour on the one large safetensors
shard).

This `huggingface_hub` version (confirmed by an actual run's deprecation
warnings, not guessed) has moved on from the old `hf_transfer` env var/
package entirely - it's Xet-based now, `HF_XET_HIGH_PERFORMANCE=1` was the
suggested replacement. Tried that first, but a live test against this exact
repo showed it hang at 0 bytes / 0% for 45+ seconds (process alive, ~2% CPU,
no progress at all) while classic HTTP started actually moving bytes within
about 2 seconds of starting - so `HF_HUB_DISABLE_XET=1` here, forcing the
plain path that's actually proven to make progress. This might just be
Xet's CAS-server endpoint being unreachable/blocked in the sandbox this was
tested in rather than a universal problem - worth trying without
HF_HUB_DISABLE_XET on a real machine if the plain path also turns out slow
there, but don't flip the default without testing first; a hang is worse
than merely-slow.

Also dropped `snapshot_download`'s `resume_download`/`local_dir_use_symlinks`
kwargs (both no-ops now - downloads always resume, symlinks are never used)
and, same footgun `download_audio8.py` already hit, `max_retries` (doesn't
exist here either) - so retries are handled by hand below, exactly like
that script's own MAX_ATTEMPTS loop. `snapshot_download` itself already
skips/resumes files already on disk in `local_dir`, so a retry after a
partial failure only re-fetches what's actually missing or incomplete.

Exits 0 on success, non-zero with a message on stderr on failure - the
caller (remanga/models/weights.py) just needs the exit code.
"""

from __future__ import annotations

import logging
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# See module docstring: Xet's high-performance path hung at 0 bytes in a
# live test against this repo - forcing the classic HTTP/LFS path instead,
# which actually moved bytes. Remove this line (or set to "0") to try Xet
# again on a connection where it might behave differently.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("MODELSCOPE_LOG_LEVEL", "40")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

MAX_ATTEMPTS = 5


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: download_deepseek_ocr.py <model_dir> <repo_id>", file=sys.stderr)
        return 2

    model_dir, repo_id = sys.argv[1], sys.argv[2]

    from huggingface_hub import snapshot_download as hf_download

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            hf_download(repo_id=repo_id, local_dir=model_dir)
            print(f">> Downloaded via Hugging Face Hub to {model_dir}")
            return 0
        except Exception as e:
            last_error = e
            print(f">> Hugging Face Hub attempt {attempt}/{MAX_ATTEMPTS} failed: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(5 * attempt, 30))

    print(f">> Hugging Face Hub failed after {MAX_ATTEMPTS} attempts ({last_error}), "
          f"falling back to ModelScope mirror...", file=sys.stderr)

    try:
        from modelscope import snapshot_download as ms_download
        ms_download(model_id=repo_id, local_dir=model_dir)
        print(f">> Downloaded via ModelScope mirror to {model_dir}")
        return 0
    except Exception as e:
        print(f"Error downloading model weights: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
