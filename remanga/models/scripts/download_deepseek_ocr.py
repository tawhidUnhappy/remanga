#!/usr/bin/env python3
"""Standalone DeepSeek-OCR-2 weight downloader - runs inside the isolated
`.venv-deepseek-ocr` environment (that's where `modelscope`/`huggingface_hub`
live; see remanga/venvs.py). Zero dependency on the `remanga` package itself.

Usage: download_deepseek_ocr.py <model_dir> <repo_id> [hf_token]

`hf_token` is optional (see remanga/hf_token.py) - only used for the HF Hub
attempts, never ModelScope (a different service/token scheme).

Three attempts, in order, each one a fresh `snapshot_download()` running in
its own subprocess so this script can actually supervise it instead of just
hoping:

  1. Hugging Face Hub, Xet enabled (HF's official high-performance transfer -
     genuinely much faster than plain HTTP when it works). WATCHED: if the
     total bytes across every `*.incomplete` file under
     `<model_dir>/.cache/huggingface/download/` haven't grown for
     XET_STALL_TIMEOUT_SECONDS (after an initial XET_STALL_GRACE_SECONDS
     warm-up), it's killed and attempt 2 runs instead. A live test against
     this exact repo once saw Xet hang at 0 bytes for 45+ seconds in one
     particular sandbox - possibly that sandbox's network blocking Xet's
     transfer-server endpoint specifically, not a fact about every machine -
     so this earns Xet a real, supervised shot instead of a blanket
     disable/enable guess either way.
  2. Hugging Face Hub, Xet explicitly disabled (classic HTTP/LFS - slower,
     but confirmed live to make steady, unstalled progress). Not watched for
     stalls the same way - MAX_ATTEMPTS retries on outright failure/
     exception instead (dropped connections etc.), same reasoning
     download_audio8.py's own retry loop already uses.
  3. ModelScope mirror, last resort - a real run once saw ITS mirror stall
     over an hour on the one large shard, which is why it's last, not first
     (opposite priority from download_indextts.py).

Every attempt's own subprocess output (tqdm progress etc.) is relayed live,
byte-for-byte, to this script's own stdout - which remanga/models/weights.py
in turn passes through stream_subprocess() the same way, so \\r-redraws
still overwrite in place all the way up to the real terminal instead of
flooding it with one line per refresh.

Also works around: `snapshot_download`'s `max_retries` kwarg not existing in
this `huggingface_hub` version (same footgun `download_audio8.py` already
hit - retries handled by hand here instead) and `resume_download`/
`local_dir_use_symlinks` being deprecated no-ops now (downloads always
resume; symlinks are never used) - so neither is passed.

Exits 0 on success, non-zero with a message on stderr on failure - the
caller (remanga/models/weights.py) just needs the exit code.
"""

from __future__ import annotations

import logging
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("MODELSCOPE_LOG_LEVEL", "40")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

MAX_ATTEMPTS = 5

# Xet-specific stall detection (see module docstring, attempt 1). Grace: how
# long to wait before judging it at all (initial CAS-server handshake can
# legitimately take a few seconds). Timeout: how long with zero byte growth,
# after the grace period, before giving up on it.
XET_STALL_GRACE_SECONDS = 15
XET_STALL_TIMEOUT_SECONDS = 20
POLL_INTERVAL_SECONDS = 2
REPORT_INTERVAL_SECONDS = 3

# The actual snapshot_download() call, run in its own subprocess (not
# imported/called directly here) so it can be killed cleanly if it stalls,
# and so its environment (HF_HUB_DISABLE_XET) can differ per attempt without
# huggingface_hub's own module-level constants (read once at import time)
# getting in the way of trying a second setting in the same process.
_DOWNLOAD_CODE = (
    "import sys\n"
    "from huggingface_hub import snapshot_download\n"
    "snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], token=(sys.argv[3] or None))\n"
)


def _fmt_bytes(n: float) -> str:
    """Human-readable byte count (e.g. '1.4GB') for the progress line below."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"  # unreachable, keeps type checkers happy


def _incomplete_bytes(model_dir: str) -> int:
    """Total size across every in-progress .incomplete file - the only
    visible sign a snapshot_download() attempt is still moving once its own
    progress bars go quiet (see the remanga-ops skill's note on
    snapshot_download's progress reporting being file-count-, not
    byte-level, once only one big file is left)."""
    d = Path(model_dir) / ".cache" / "huggingface" / "download"
    if not d.is_dir():
        return 0
    total = 0
    for f in d.glob("*.incomplete"):
        try:
            total += f.stat().st_size
        except OSError:
            pass  # file finished/renamed between glob() and stat() - fine, just skip it
    return total


def _run_hf_attempt(
    model_dir: str, repo_id: str, hf_token: Optional[str], disable_xet: bool,
    stall_timeout: Optional[float], label: str,
) -> bool:
    """Runs one snapshot_download() attempt as a child subprocess, relaying
    its output live. If `stall_timeout` is set, kills it and returns False
    once XET_STALL_GRACE_SECONDS + stall_timeout have passed with no growth
    in _incomplete_bytes(); otherwise just waits for it to exit normally.
    Returns True on a clean (exit 0) completion."""
    env = os.environ.copy()
    env["HF_HUB_DISABLE_XET"] = "1" if disable_xet else "0"

    print(f">> [{label}] starting...")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _DOWNLOAD_CODE, repo_id, model_dir, hf_token or ""],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
    )

    start = time.time()
    last_bytes = _incomplete_bytes(model_dir)
    last_growth = start
    last_report = start
    reported_any = False

    while True:
        ready, _, _ = select.select([proc.stdout], [], [], POLL_INTERVAL_SECONDS)
        if ready:
            chunk = proc.stdout.read(65536)
            if chunk:
                os.write(1, chunk)  # relay raw bytes - preserves \r redraws all the way up
            elif proc.poll() is not None:
                break  # EOF and process gone - done

        if proc.poll() is not None:
            break

        now = time.time()
        cur_bytes = _incomplete_bytes(model_dir)
        if cur_bytes > last_bytes:
            last_bytes = cur_bytes
            last_growth = now

        # Byte-level progress line, independent of whatever (if anything)
        # the child's own tqdm/Xet output is printing. Needed because
        # snapshot_download's own "Fetching N files" bar only tracks
        # file-COUNT completion - for a repo dominated by one giant shard
        # (N=1, exactly DeepSeek-OCR-2 and IndexTTS-2.5's case) that bar sits
        # at "0/1" for the entire multi-GB transfer, so without this the
        # console goes dark for however long that takes. Throttled to once
        # every REPORT_INTERVAL_SECONDS so it doesn't fight the child's own
        # \r-redraws for the line.
        if now - last_report >= REPORT_INTERVAL_SECONDS:
            elapsed = now - start
            rate = cur_bytes / elapsed if elapsed > 0 else 0
            print(f"\r>> [{label}] {_fmt_bytes(cur_bytes)} downloaded ({_fmt_bytes(rate)}/s)"
                  + " " * 10, end="", flush=True)
            last_report = now
            reported_any = True

        if stall_timeout is not None and now - start > XET_STALL_GRACE_SECONDS \
                and now - last_growth > stall_timeout:
            print(f"\n>> [{label}] no download progress for {stall_timeout:.0f}s - "
                  f"giving up on this path and trying the next one...", file=sys.stderr)
            proc.kill()
            proc.wait(timeout=5)
            return False

    if reported_any:
        print()  # leave our last \r-progress line intact instead of letting the next print overwrite it

    return proc.wait() == 0


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("Usage: download_deepseek_ocr.py <model_dir> <repo_id> [hf_token]", file=sys.stderr)
        return 2

    model_dir, repo_id = sys.argv[1], sys.argv[2]
    hf_token = sys.argv[3] if len(sys.argv) == 4 else None

    # Attempt 1: HF Hub, Xet enabled, supervised for stalls.
    if _run_hf_attempt(model_dir, repo_id, hf_token, disable_xet=False,
                        stall_timeout=XET_STALL_TIMEOUT_SECONDS, label="HF Hub, Xet"):
        print(f">> Downloaded via Hugging Face Hub to {model_dir}")
        return 0

    # Attempt 2: HF Hub, Xet disabled (classic HTTP) - proven to make steady
    # progress even when slow. Retried MAX_ATTEMPTS times on outright
    # failure (dropped connection etc.), not stall-supervised the same way.
    last_ok = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        last_ok = _run_hf_attempt(model_dir, repo_id, hf_token, disable_xet=True,
                                   stall_timeout=None, label=f"HF Hub, classic HTTP, attempt {attempt}/{MAX_ATTEMPTS}")
        if last_ok:
            break
        if attempt < MAX_ATTEMPTS:
            time.sleep(min(5 * attempt, 30))
    if last_ok:
        print(f">> Downloaded via Hugging Face Hub to {model_dir}")
        return 0

    print(">> Hugging Face Hub failed (both Xet and classic HTTP), "
          "falling back to ModelScope mirror...", file=sys.stderr)

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
