from __future__ import annotations

import subprocess
from pathlib import Path
from rich.console import Console

from remanga.venvs import get_scripts_dir, get_tool_python

console = Console()


class ModelManager:
    """Ensures IndexTTS-2.5 weights are present, downloading them via the
    isolated `.venv-indextts` environment's own modelscope/huggingface_hub
    install (those packages aren't part of the main env - see remanga/venvs.py)."""

    def __init__(self, model_dir: Path | str = "checkpoints/indextts_2.5", repo_id: str = "IndexTeam/IndexTTS-2.5"):
        self.model_dir = Path(model_dir)
        self.repo_id = repo_id

    def ensure_model(self) -> Path:
        """Downloads or verifies model weights cleanly without stdout spamming."""
        self.model_dir.mkdir(parents=True, exist_ok=True)

        gpt_path = self.model_dir / "gpt.pth"
        s2mel_path = self.model_dir / "s2mel.pth"

        # Check if already present to skip unnecessary network hits (and the
        # subprocess spin-up entirely)
        if gpt_path.exists() and s2mel_path.exists() and gpt_path.stat().st_size > 100000:
            return self.model_dir

        python = get_tool_python("indextts")
        script = get_scripts_dir("models") / "download_indextts.py"

        with console.status(f"[bold cyan]Verifying IndexTTS-2.5 model weights ({self.repo_id})...[/]", spinner="dots"):
            result = subprocess.run(
                [str(python), str(script), str(self.model_dir.resolve()), self.repo_id],
                capture_output=True, text=True,
            )

        if result.returncode != 0:
            console.print(f"[bold red]Error downloading model weights:[/] {result.stderr.strip()}")
            raise RuntimeError(f"IndexTTS-2.5 weight download failed: {result.stderr.strip()}")

        console.print("[bold green]✓ IndexTTS-2.5 model weights verified and ready![/]")
        return self.model_dir
