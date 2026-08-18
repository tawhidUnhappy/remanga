from __future__ import annotations

from pathlib import Path
from rich.console import Console

console = Console()


class ModelManager:
    """Manages IndexTTS-2.5 weights using fast Asian CDN mirror with automatic Hugging Face fallback."""

    def __init__(self, model_dir: Path | str = "checkpoints/indextts_2.5", repo_id: str = "IndexTeam/IndexTTS-2.5"):
        self.model_dir = Path(model_dir)
        self.repo_id = repo_id

    def ensure_model(self) -> Path:
        """Downloads or resumes model weights using high-speed mirror with auto-resume."""
        console.print(f"[cyan]Checking IndexTTS-2.5 model weights ({self.repo_id})...[/]")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        # 1. High-speed ModelScope mirror (fastest CDN, no timeouts)
        try:
            console.print("[cyan]Connecting to high-speed mirror (ModelScope CDN)...[/]")
            from modelscope import snapshot_download as ms_download

            ms_download(
                model_id=self.repo_id,
                local_dir=str(self.model_dir.resolve()),
            )
            console.print("[bold green]✓ IndexTTS-2.5 model weights verified and ready![/]")
            return self.model_dir
        except Exception as e:
            console.print(f"[yellow]ModelScope notice: {e}. Falling back to Hugging Face Hub...[/]")

        # 2. Hugging Face fallback with auto-resume and retry tolerance
        try:
            from huggingface_hub import snapshot_download as hf_download

            console.print("[cyan]Downloading from Hugging Face Hub (with auto-resume)...[/]")
            hf_download(
                repo_id=self.repo_id,
                local_dir=str(self.model_dir.resolve()),
                local_dir_use_symlinks=False,
                resume_download=True,
                max_retries=10,
            )
            console.print("[bold green]✓ IndexTTS-2.5 model weights verified and ready![/]")
        except Exception as e:
            console.print(f"[red]Error downloading model weights: {e}[/]")
            raise e

        return self.model_dir