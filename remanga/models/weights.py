from __future__ import annotations

from pathlib import Path
from typing import Sequence

from remanga.console import console
from remanga.hf_token import resolve_hf_token
from remanga.proc_io import stream_subprocess
from remanga.venvs import get_scripts_dir, get_tool_python


class ModelManager:
    """Ensures a model's weights are present, downloading them via its own
    isolated `.tools/venv-<tool_name>` environment's modelscope/huggingface_hub
    install (those packages aren't part of the main env - see remanga/venvs.py).

    Generic across every TTS engine remanga supports (IndexTTS-2.5, Audio8
    TTS, ...) - what differs per engine is just which isolated venv talks to
    the Hub, which download script it runs, and which files on disk prove the
    download actually finished; everything else (skip-if-present check, the
    status spinner, error handling) is identical."""

    def __init__(
        self,
        model_dir: Path | str,
        repo_id: str,
        tool_name: str = "indextts",
        download_script: str = "download_indextts.py",
        expected_files: Sequence[str] = ("gpt.pth", "s2mel.pth"),
        display_name: str = "IndexTTS-2.5",
    ):
        self.model_dir = Path(model_dir)
        self.repo_id = repo_id
        self.tool_name = tool_name
        self.download_script = download_script
        self.expected_files = list(expected_files)
        self.display_name = display_name

    def ensure_model(self) -> Path:
        """Downloads or verifies model weights cleanly without stdout spamming."""
        self.model_dir.mkdir(parents=True, exist_ok=True)

        # Check if already present to skip unnecessary network hits (and the
        # subprocess spin-up entirely)
        if all((self.model_dir / f).exists() and (self.model_dir / f).stat().st_size > 100000 for f in self.expected_files):
            return self.model_dir

        python = get_tool_python(self.tool_name)
        script = get_scripts_dir("models") / self.download_script

        # Optional 3rd positional arg every download script accepts (see
        # remanga/hf_token.py) - None/empty stays fully backward compatible
        # with a script that ignores a missing arg entirely.
        token = resolve_hf_token()
        # -u (unbuffered stdout/stderr): without it, CPython switches from
        # line-buffered to block-buffered the moment stdout isn't a real
        # terminal (i.e. always, once piped through subprocess.PIPE here) -
        # tqdm's own small \r-updates then sit in that buffer instead of
        # actually reaching this process, so the console looks completely
        # stalled ("Downloading..." and then nothing) even though the
        # download is progressing fine underneath. Same reasoning every
        # worker subprocess spawn elsewhere already applies (indextts_worker/
        # audio8_worker/deepseek_ocr_worker's own -u flag).
        cmd = [str(python), "-u", str(script), str(self.model_dir.resolve()), self.repo_id]
        if token:
            cmd.append(token)

        console.print(f"[bold cyan]Downloading {self.display_name} model weights ({self.repo_id})...[/]")
        # Streamed live (not capture_output=True) - huggingface_hub's own
        # snapshot_download() progress bars (tqdm, one per file) live on
        # stderr, and a full multi-GB download can take tens of minutes.
        # Buffering all of it until the subprocess exits - the previous
        # behavior - left the console looking completely stalled for that
        # entire time, only ever dumping the buffered output at the very end
        # (and only on failure). stream_subprocess overwrites tqdm's
        # \r-terminated redraws in place (like a real terminal would) instead
        # of flooding the console with one new line per refresh.
        returncode, output = stream_subprocess(cmd)

        if returncode != 0:
            tail = output.strip()
            console.print(f"[bold red]Error downloading model weights:[/] {tail}")
            raise RuntimeError(f"{self.display_name} weight download failed: {tail}")

        console.print(f"[bold green]✓ {self.display_name} model weights verified and ready![/]")
        return self.model_dir
