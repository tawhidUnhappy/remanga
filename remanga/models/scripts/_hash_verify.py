#!/usr/bin/env python3
"""Shared post-download SHA256 verification, used by every standalone weight
downloader in this repo (download_indextts.py, download_audio8.py,
download_deepseek_ocr.py, and webui/scripts/download_magi.py).

Why this exists: huggingface_hub's own snapshot_download() only checks that
each downloaded file's *size* matches what the server reported ("Consistency
check failed: file should be of size X but has size Y") - it never recomputes
a file's hash and compares it to the repo's recorded one. That catches a
truncated/cut-short transfer, but not silent bit-rot (a disk hiccup, a flaky
USB drive, a corrupted resume) that happens to land on the right byte count.
This module closes that gap by pulling each file's real SHA256 straight from
the Hub's own git-LFS metadata (`sibling.lfs.sha256` - the same hash `git
lfs` itself uses to verify a checkout) and comparing it against a local
hashlib.sha256() of the file actually sitting on disk.

Kept dependency-free beyond `huggingface_hub` (already required by every
caller) and importable via a plain sys.path insert from a sibling scripts/
directory (webui/scripts/download_magi.py does this) - none of these
downloaders assume the `remanga` package itself is installed in their
isolated venv, so this can't import from remanga.* either.

Non-LFS files (small text/config files, hashed by git as plain SHA1 blobs)
are skipped - they're tiny, never the actual corruption risk this guards
against, and their git blob hash isn't cheaply comparable to a local file's
sha256 anyway.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _resolve_local_path(model_dir: str, rfilename: str, cache_layout: bool) -> Optional[Path]:
    """Finds where `rfilename` actually landed on disk. `local_dir=` downloads
    (indextts/audio8/deepseek_ocr) put it directly at model_dir/rfilename.
    `cache_dir=` downloads (magi) put the real blob under
    <model_dir>/models--<org>--<repo>/blobs/<hash>, symlinked from
    snapshots/<revision>/rfilename - os.path.realpath() follows that straight
    to the blob."""
    if not cache_layout:
        p = Path(model_dir) / rfilename
        return p if p.is_file() else None

    cache_root = Path(model_dir)
    for model_hub_dir in cache_root.glob("models--*"):
        for snapshot_dir in (model_hub_dir / "snapshots").glob("*"):
            candidate = snapshot_dir / rfilename
            if candidate.exists():
                return Path(os.path.realpath(candidate))
    return None


def verify_repo_files(
    model_dir: str, repo_id: str, hf_token: Optional[str], cache_layout: bool = False,
) -> tuple[bool, list[str]]:
    """Compares every LFS file's recorded sha256 (from the Hub's own repo
    metadata) against the freshly-downloaded file on disk. Prints one line
    per mismatch/missing file and a final summary. Returns (ok, bad_rfilenames)
    - ok is True only if every LFS file checked out clean; bad_rfilenames
    lists the ones that didn't, so a caller can delete just those and retry
    instead of re-fetching the whole snapshot. Never raises on its own - a
    metadata-fetch failure (offline, rate-limited, private repo without
    files_metadata access) is reported and treated as "could not verify",
    not a hard failure, since the download itself already succeeded."""
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(repo_id, token=hf_token, files_metadata=True)
    except Exception as e:
        print(f">> Hash verification skipped (could not fetch repo metadata: {e})")
        return True, []

    lfs_siblings = [s for s in info.siblings if s.lfs is not None and s.lfs.get("sha256")]
    if not lfs_siblings:
        print(">> Hash verification skipped (no LFS files with a recorded sha256 in this repo)")
        return True, []

    print(f">> Verifying SHA256 for {len(lfs_siblings)} file(s)...")
    bad: list[str] = []
    for sibling in lfs_siblings:
        expected = sibling.lfs["sha256"]
        local_path = _resolve_local_path(model_dir, sibling.rfilename, cache_layout)
        if local_path is None:
            print(f"   ✗ {sibling.rfilename}: file not found on disk after download")
            bad.append(sibling.rfilename)
            continue
        actual = _sha256_file(local_path)
        if actual != expected:
            print(f"   ✗ {sibling.rfilename}: hash mismatch (expected {expected[:12]}..., got {actual[:12]}...)")
            bad.append(sibling.rfilename)
        else:
            print(f"   ✓ {sibling.rfilename}")

    if bad:
        print(f">> {len(bad)}/{len(lfs_siblings)} file(s) failed verification: {', '.join(bad)}")
        return False, bad

    print(f">> All {len(lfs_siblings)} file(s) verified against the Hub's recorded SHA256.")
    return True, []


def delete_files_for_retry(model_dir: str, rfilenames: list[str], cache_layout: bool) -> None:
    """Removes locally-corrupt/missing files so a follow-up snapshot_download
    actually re-fetches them - snapshot_download only skips files that are
    already *present* (by size), so leaving a corrupt one in place would make
    a retry silently reuse the same bad bytes."""
    for rfilename in rfilenames:
        local_path = _resolve_local_path(model_dir, rfilename, cache_layout)
        if local_path is not None and local_path.exists():
            local_path.unlink()
        if cache_layout:
            # Also drop the snapshot symlink itself (points at the blob we
            # just deleted) so the directory doesn't keep a dangling entry.
            for model_hub_dir in Path(model_dir).glob("models--*"):
                for snapshot_dir in (model_hub_dir / "snapshots").glob("*"):
                    link = snapshot_dir / rfilename
                    if link.is_symlink() or link.exists():
                        link.unlink(missing_ok=True)
        else:
            # local_dir layout also leaves a .cache/huggingface/download/
            # <file>.metadata sidecar recording the etag/size snapshot_download
            # already saw - stale after we delete the file, so drop it too.
            meta = Path(model_dir) / ".cache" / "huggingface" / "download" / f"{rfilename}.metadata"
            meta.unlink(missing_ok=True)
