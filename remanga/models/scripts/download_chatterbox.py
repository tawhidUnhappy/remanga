#!/usr/bin/env python3
"""Standalone Chatterbox Turbo weight downloader - runs inside the isolated
`.tools/venv-chatterbox` environment (that's where `huggingface_hub` lives;
see remanga/venvs.py). Zero dependency on the `remanga` package itself.

Usage: download_chatterbox.py <model_dir> <repo_id> [hf_token]
Exits 0 on success, non-zero with a message on stderr on failure - the
caller (remanga/models/weights.py) just needs the exit code.

Fetches the files `ChatterboxTurboTTS.from_local` opens, not the whole repo.
ResembleAI/chatterbox-turbo also carries `s3gen.safetensors` - the original
model's 1GB decoder, which Turbo never loads (it decodes with
`s3gen_meanflow.safetensors`) - and upstream's own `from_pretrained` pulls
every *.safetensors, so it fetches that gigabyte anyway.

Xet is disabled and each attempt is a plain retry. Xet transfers have hung
at 0 bytes on this project before - no error, no timeout, no progress (see
the remanga-ops skill's download notes) - while classic HTTP is slower but
finishes. Every LFS file fetched is then checked against the Hub's recorded
SHA256 (_hash_verify.py), with one re-fetch of anything that fails.

`hf_token` is optional (see remanga/hf_token.py); the repo is public and
ungated.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Read by huggingface_hub when it is imported, so set before that happens.
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hash_verify import delete_files_for_retry, verify_repo_files

# The three checkpoints are named so s3gen.safetensors is not matched; the
# tokenizer files are matched by pattern because AutoTokenizer reads
# whichever of them the repo ships.
ALLOW_PATTERNS = [
    "ve.safetensors", "t3_turbo_v1.safetensors", "s3gen_meanflow.safetensors",
    "conds.pt", "*.json", "*.txt",
]
REQUIRED_FILES = (
    "ve.safetensors", "t3_turbo_v1.safetensors", "s3gen_meanflow.safetensors",
    "vocab.json", "merges.txt", "tokenizer_config.json",
)
MAX_ATTEMPTS = 3


def _download(repo_id: str, model_dir: Path, token: str | None) -> bool:
    from huggingface_hub import snapshot_download

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            snapshot_download(
                repo_id=repo_id, local_dir=str(model_dir),
                allow_patterns=ALLOW_PATTERNS, token=token,
            )
            return True
        except Exception as e:
            print(f">> Download attempt {attempt}/{MAX_ATTEMPTS} failed: {e}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                time.sleep(5 * attempt)
    return False


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: download_chatterbox.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir = Path(sys.argv[1]).resolve()
    repo_id = sys.argv[2]
    token = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3].strip() else None

    try:
        import huggingface_hub  # noqa: F401
    except ImportError as e:
        print(f"huggingface_hub is not installed in this environment: {e}", file=sys.stderr)
        return 1

    model_dir.mkdir(parents=True, exist_ok=True)

    if not _download(repo_id, model_dir, token):
        print(f"Failed to download {repo_id}.", file=sys.stderr)
        return 1

    ok, bad = verify_repo_files(str(model_dir), repo_id, token, allow_patterns=ALLOW_PATTERNS)
    if not ok:
        print(f">> Re-fetching {len(bad)} file(s) that failed verification...")
        delete_files_for_retry(str(model_dir), bad, cache_layout=False)
        if not _download(repo_id, model_dir, token):
            print(f"Failed to re-download {', '.join(bad)}.", file=sys.stderr)
            return 1
        ok, bad = verify_repo_files(str(model_dir), repo_id, token, allow_patterns=ALLOW_PATTERNS)
        if not ok:
            print(f"{len(bad)} file(s) still fail hash verification: {', '.join(bad)}", file=sys.stderr)
            return 1

    missing = [name for name in REQUIRED_FILES if not (model_dir / name).is_file()]
    if missing:
        print(f"Download finished but {', '.join(missing)} did not land in {model_dir}.", file=sys.stderr)
        return 1

    print(f"Chatterbox Turbo ready in {model_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
