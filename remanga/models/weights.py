from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from rich.console import Console

console = Console()

# Suppress noisy download bar spamming across submodules
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["MODELSCOPE_LOG_LEVEL"] = "40"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


class ModelManager:
    """Manages IndexTTS-2.5 weights with clean status indicators and fallback tolerance."""

    def __init__(self, model_dir: Path | str = "checkpoints/indextts_2.5", repo_id: str = "IndexTeam/IndexTTS-2.5"):
        self.model_dir = Path(model_dir)
        self.repo_id = repo_id

    def ensure_model(self) -> Path:
        """Downloads or verifies model weights cleanly without stdout spamming."""
        self.model_dir.mkdir(parents=True, exist_ok=True)

        gpt_path = self.model_dir / "gpt.pth"
        s2mel_path = self.model_dir / "s2mel.pth"

        # Check if already present to skip unnecessary network hits
        if gpt_path.exists() and s2mel_path.exists() and gpt_path.stat().st_size > 100000:
            return self.model_dir

        with console.status(f"[bold cyan]Verifying IndexTTS-2.5 model weights ({self.repo_id})...[/]", spinner="dots"):
            # 1. High-speed ModelScope mirror
            try:
                from modelscope import snapshot_download as ms_download

                ms_download(
                    model_id=self.repo_id,
                    local_dir=str(self.model_dir.resolve()),
                )
                console.print("[bold green]✓ IndexTTS-2.5 model weights verified and ready![/]")
                return self.model_dir
            except Exception as e:
                pass

            # 2. Hugging Face Hub Fallback
            try:
                from huggingface_hub import snapshot_download as hf_download

                hf_download(
                    repo_id=self.repo_id,
                    local_dir=str(self.model_dir.resolve()),
                    local_dir_use_symlinks=False,
                    resume_download=True,
                    max_retries=10,
                )
                console.print("[bold green]✓ IndexTTS-2.5 model weights verified and ready![/]")
            except Exception as e:
                console.print(f"[bold red]Error downloading model weights:[/] {e}")
                raise e

        return self.model_dir