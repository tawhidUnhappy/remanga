#!/usr/bin/env python3
"""Standalone DeepSeek-OCR-2 weight downloader - runs inside the isolated
`.venv-deepseek-ocr` environment (that's where `modelscope`/`huggingface_hub`
live; see remanga/venvs.py). Zero dependency on the `remanga` package itself.

Usage: download_deepseek_ocr.py <model_dir> <repo_id>

Tries the Hugging Face Hub first, with `hf_transfer` enabled - HF's own
official Rust-based accelerated client (multi-connection chunked transfer
for large files, same CDN, nothing unofficial or ToS-adjacent about it: see
https://huggingface.co/docs/huggingface_hub/hf_transfer). Falls back to the
ModelScope mirror if that fails.

This is the opposite priority from download_indextts.py (ModelScope first,
HF fallback) - flipped here because a real run against this exact repo saw
ModelScope's own CDN stall for over an hour on the single ~6.8GB safetensors
shard (repeated read-timeout retries, one hash-validation retry that itself
took over 90 minutes) while regular HF+hf_transfer downloads are typically
multiple times faster for one big file like this. If ModelScope's mirror for
this repo turns out to be fine on a different network, flip the order back -
this isn't a blanket "ModelScope is bad" verdict, just what actually
happened downloading *this* model on *this* connection.

Exits 0 on success, non-zero with a message on stderr on failure - the
caller (remanga/models/weights.py) just needs the exit code.
"""

from __future__ import annotations

import logging
import os
import sys

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# On, not off (see download_indextts.py's "0" default) - this venv actually
# has `hf_transfer` installed (bootstrap.sh) specifically for this script.
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
os.environ.setdefault("MODELSCOPE_LOG_LEVEL", "40")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: download_deepseek_ocr.py <model_dir> <repo_id>", file=sys.stderr)
        return 2

    model_dir, repo_id = sys.argv[1], sys.argv[2]

    try:
        from huggingface_hub import snapshot_download as hf_download
        hf_download(
            repo_id=repo_id,
            local_dir=model_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
            max_retries=10,
        )
        print(f">> Downloaded via Hugging Face Hub (hf_transfer) to {model_dir}")
        return 0
    except Exception as e:
        print(f">> Hugging Face Hub failed ({e}), falling back to ModelScope mirror...", file=sys.stderr)

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
