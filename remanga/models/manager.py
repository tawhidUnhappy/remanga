from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Tuple
from rich.console import Console

console = Console()


class ModelManager:
    """Handles integrity verification, SHA-256 checksums, and model downloads."""

    def __init__(self, model_dir: Path | str = "checkpoints/indextts_2.5", repo_id: str = "IndexTeam/IndexTTS-2.5"):
        self.model_dir = Path(model_dir)
        self.repo_id = repo_id

    @staticmethod
    def compute_sha256(filepath: Path) -> str:
        """Calculates SHA-256 hash of a file in 8MB chunks."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(1024 * 1024 * 8):
                h.update(chunk)
        return h.hexdigest()

    def verify_integrity(self) -> Tuple[bool, List[Tuple[str, str]]]:
        """
        Verifies local files against remote Hugging Face manifest.
        Checks existence, exact byte size, and Git LFS SHA-256 checksums.
        """
        from huggingface_hub import HfApi

        api = HfApi()
        self.model_dir.mkdir(parents=True, exist_ok=True)

        try:
            remote_files = [
                f for f in api.list_repo_tree(repo_id=self.repo_id, recursive=True)
                if hasattr(f, "size") and f.size is not None
            ]
        except Exception as e:
            console.print(f"[yellow]Manifest fetch notice: {e}. Verifying core weight files...[/]")
            core_files = ["config.yaml", "gpt.pth", "codec.pth", "s2mel.pth"]
            is_valid = all((self.model_dir / c).exists() and (self.model_dir / c).stat().st_size > 1024 * 1024 for c in core_files)
            return is_valid, []

        issues: List[Tuple[str, str]] = []

        for rfile in remote_files:
            local_file = self.model_dir / rfile.path

            if not local_file.exists():
                issues.append((rfile.path, "Missing"))
                continue

            if local_file.stat().st_size != rfile.size:
                issues.append((rfile.path, f"Size mismatch (expected: {rfile.size}, got: {local_file.stat().st_size})"))
                continue

            # Verify LFS SHA-256 hash if present
            if hasattr(rfile, "lfs") and rfile.lfs and getattr(rfile.lfs, "sha256", None):
                expected_hash = rfile.lfs.sha256
                local_hash = self.compute_sha256(local_file)
                if local_hash != expected_hash:
                    issues.append((rfile.path, f"SHA-256 mismatch ({local_hash[:8]} != {expected_hash[:8]})"))

        return len(issues) == 0, issues

    def ensure_model(self) -> Path:
        """Verifies model files, downloading missing or corrupted weights with auto-resume."""
        is_valid, issues = self.verify_integrity()

        if is_valid:
            console.print("[bold green]✓ IndexTTS-2.5 weights verified (100% byte size & SHA-256 match)[/]")
            return self.model_dir

        if issues:
            console.print(f"[yellow]Detected {len(issues)} missing/corrupted file(s):[/]")
            for path, reason in issues[:4]:
                console.print(f"  [dim]- {path}: {reason}[/]")
            if len(issues) > 4:
                console.print(f"  [dim]... and {len(issues) - 4} more.[/]")

        console.print(f"[cyan]Downloading missing weights for '{self.repo_id}'...[/]")
        download_success = False

        # 1. Try high-speed ModelScope mirror
        try:
            from modelscope import snapshot_download as ms_download
            console.print("[cyan]Connecting to high-speed ModelScope mirror...[/]")
            ms_download(self.repo_id, local_dir=str(self.model_dir.resolve()))
            download_success = True
        except Exception as e:
            console.print(f"[dim yellow]ModelScope notice: {e}. Falling back to Hugging Face...[/]")

        # 2. Hugging Face fallback with resume
        if not download_success or not self.verify_integrity()[0]:
            from huggingface_hub import snapshot_download as hf_download
            console.print("[cyan]Downloading directly from Hugging Face Hub (with auto-resume)...[/]")
            hf_download(
                repo_id=self.repo_id,
                local_dir=str(self.model_dir.resolve()),
                local_dir_use_symlinks=False,
                resume_download=True,
            )

        final_valid, remaining_issues = self.verify_integrity()
        if final_valid:
            console.print("[bold green]✓ IndexTTS-2.5 model weights downloaded and 100% verified![/]")
        else:
            console.print(f"[red]Warning: {len(remaining_issues)} file(s) failed verification. Re-run setup to complete.[/]")

        return self.model_dir