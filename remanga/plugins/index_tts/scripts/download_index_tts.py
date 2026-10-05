#!/usr/bin/env python3
"""Standalone IndexTTS-2.5 weight downloader - runs inside the isolated
`.tools/venv-index-tts` environment (that's where `huggingface_hub` and
`indextts` live; see remanga/tool_envs/). Zero dependency on the `remanga`
package itself.

Usage: download_index_tts.py <model_dir> <repo_id> [hf_token]
Exits 0 on success, non-zero with a message on stderr on failure - the caller
(remanga/models/weights.py) just needs the exit code.

Two parts: the checkpoint itself (`repo_id`, config.yaml and the weights it
names), then the four models IndexTTS loads beside it - w2v-bert-2.0, the
MaskGCT semantic codec, CAM++ and BigVGAN - which upstream's own
ensure_models_available() puts in <model_dir>/hf_cache/. Fetching those here
rather than on the worker's first start keeps a multi-GB download out of the
synthesis timeout.

Xet is disabled and each attempt is a plain retry, as in download_qwen_tts.py:
Xet transfers have hung at 0 bytes on this project before.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Read by huggingface_hub when it is imported, so set before that happens.
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

REQUIRED_FILES = ("config.yaml", "gpt.pth", "s2mel.pth", "codec.pth")
# The Qwen model that reads an emotion out of the text (use_qwen_emo) - 1.2 GB
# remanga never loads: narration keeps one steady register, so nothing asks
# the model for an emotion at all.
IGNORE_PATTERNS = ["qwen0.6bemo4-merge/*"]
MAX_ATTEMPTS = 3


def _retry(what: str, step) -> bool:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            step()
            return True
        except Exception as e:
            print(f">> {what}: attempt {attempt}/{MAX_ATTEMPTS} failed: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                time.sleep(5 * attempt)
    return False


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: download_index_tts.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir = Path(sys.argv[1]).resolve()
    repo_id = sys.argv[2]
    token = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3].strip() else None
    model_dir.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import snapshot_download

    if not _retry(repo_id, lambda: snapshot_download(
        repo_id=repo_id, local_dir=str(model_dir), ignore_patterns=IGNORE_PATTERNS, token=token)):
        print(f"Failed to download {repo_id}.", file=sys.stderr)
        return 1
    missing = [name for name in REQUIRED_FILES if not (model_dir / name).is_file()]
    if missing:
        print(f"Download finished but {', '.join(missing)} did not land in {model_dir}.", file=sys.stderr)
        return 1

    from indextts.utils.model_download import ensure_models_available

    if not _retry("auxiliary models", lambda: ensure_models_available(str(model_dir))):
        print("Failed to download IndexTTS's auxiliary models.", file=sys.stderr)
        return 1

    print(f"{repo_id} ready in {model_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
