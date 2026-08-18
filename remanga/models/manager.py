from __future__ import annotations

from pathlib import Path
from huggingface_hub import snapshot_download
from rich.console import Console

console = Console()


class ModelManager:
    """Manages IndexTTS-2.5 weights using native Hugging Face Hub verification and caching."""

    def __init__(self, model_dir: Path | str = "checkpoints/indextts_2.5", repo_id: str = "IndexTeam/IndexTTS-2.5"):
        self.model_dir = Path(model_dir)
        self.repo_id = repo_id

    def ensure_model(self) -> Path:
        """Natively checks, resumes, and verifies model weights using Hugging Face Hub."""
        console.print(f"[cyan]Checking IndexTTS-2.5 model weights ({self.repo_id})...[/]")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        try:
            snapshot_download(
                repo_id=self.repo_id,
                local_dir=str(self.model_dir.resolve()),
                local_dir_use_symlinks=False,
            )
            console.print("[bold green]✓ IndexTTS-2.5 model weights verified and ready![/]")
        except Exception as e:
            console.print(f"[red]Error downloading model weights: {e}[/]")
            raise e

        return self.model_dir