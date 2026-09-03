#!/usr/bin/env python3
"""Standalone DeepSeek-OCR-2 weight downloader - runs inside the isolated
`.venv-deepseek-ocr` environment (that's where `modelscope`/`huggingface_hub`
live; see remanga/venvs.py). Zero dependency on the `remanga` package itself.
Mirrors remanga/models/scripts/download_indextts.py's shape exactly.

Usage: download_deepseek_ocr.py <model_dir> <repo_id>
Tries the ModelScope CDN mirror first (usually much faster, and deepseek-ai
repos are commonly mirrored there), falls back to the Hugging Face Hub.
Exits 0 on success, non-zero with a message on stderr on failure - the
caller (remanga/models/weights.py) just needs the exit code.
"""

from __future__ import annotations

import logging
import os
import sys

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
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
        from modelscope import snapshot_download as ms_download
        ms_download(model_id=repo_id, local_dir=model_dir)
        print(f">> Downloaded via ModelScope mirror to {model_dir}")
        return 0
    except Exception as e:
        print(f">> ModelScope mirror failed ({e}), falling back to Hugging Face Hub...", file=sys.stderr)

    try:
        from huggingface_hub import snapshot_download as hf_download
        hf_download(
            repo_id=repo_id,
            local_dir=model_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
            max_retries=10,
        )
        print(f">> Downloaded via Hugging Face Hub to {model_dir}")
        return 0
    except Exception as e:
        print(f"Error downloading model weights: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
