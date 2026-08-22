"""Low-level IndexTTS-2.5 speech synthesis: spawns and talks to the isolated
`.venv-indextts` worker process (remanga/audio/scripts/indextts_worker.py) so
IndexTTS's own dependency pins never have to share a Python process - or a
dependency resolution - with the rest of remanga or with MAGI v3's isolated
environment. See remanga/venvs.py for how that environment is located."""

from __future__ import annotations

import atexit
import json
import subprocess
from pathlib import Path
from typing import List, Optional
from pydub import AudioSegment
from rich.console import Console

from remanga.config import AudioConfig, TTSConfig
from remanga.ffmpeg_io import run_ffmpeg
from remanga.models import ModelManager
from remanga.venvs import REPO_ROOT, extract_missing_packages, get_scripts_dir, get_tool_python

console = Console()
_MAX_AUTO_HEAL_ATTEMPTS = 8


def _pip_install_into_indextts_env(packages: set) -> bool:
    """Installs `packages` into `.venv-indextts`, preferring this repo's own
    `bin/uv` (that isolated venv has no `pip` module at all)."""
    names = sorted(packages)
    console.print(f"[yellow]Installing missing dependency into .venv-indextts: {' '.join(names)}...[/]")

    uv_bin = REPO_ROOT / "bin" / "uv"
    python = get_tool_python("indextts")
    cmd = [str(uv_bin), "pip", "install", "--python", str(python), *names] if uv_bin.exists() \
        else [str(python), "-m", "pip", "install", *names]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"[bold red]Failed to install {' '.join(names)} automatically.[/]")
        return False
    console.print(f"[bold green]✓ Installed {' '.join(names)}.[/]")
    return True


class IndexTTSSynthesizer:
    """Owns one long-lived `.venv-indextts` worker subprocess and speaks to it
    over stdin/stdout for every synthesize() call, so the model loads onto the
    GPU once per production run instead of once per panel."""

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.audio_config = audio_config
        self.model_manager = ModelManager(tts_config.model_dir, tts_config.hf_repo_id)
        self._proc: Optional[subprocess.Popen] = None
        atexit.register(self.shutdown)

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        python = get_tool_python("indextts")
        script = get_scripts_dir("audio") / "indextts_worker.py"

        cmd: List[str] = [
            str(python), "-u", str(script),
            "--cfg_path", str(Path(self.tts_config.cfg_path).resolve()),
            "--model_dir", str(model_dir.resolve()),
        ]
        if self.tts_config.use_bf16:
            cmd.append("--use_bf16")

        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _ensure_worker(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc

        model_dir = self.model_manager.ensure_model()
        console.print("[cyan]Starting IndexTTS-2.5 worker...[/]")

        # Auto-heal: a missing dependency IndexTTS's own install didn't pin
        # (bootstrap.sh's fixed package list, or a future IndexTTS revision
        # that imports something new) gets installed into .venv-indextts and
        # retried, instead of raising mid-session over something one pip
        # install would have fixed. See remanga/webui/magi_assist.py for the
        # same pattern against MAGI v3's own isolated env.
        attempted: set = set()
        for _ in range(_MAX_AUTO_HEAL_ATTEMPTS + 1):
            proc = self._spawn_worker(model_dir)
            ready_line = proc.stdout.readline()
            if not ready_line:
                stderr = proc.stderr.read()
                raise RuntimeError(f"IndexTTS-2.5 worker exited before starting up:\n{stderr}")

            event = json.loads(ready_line)
            if event.get("event") == "ready":
                console.print("[bold green]✓ IndexTTS-2.5 worker ready.[/]")
                self._proc = proc
                return proc

            error_text = event.get("error", "")
            missing = extract_missing_packages(error_text) - attempted
            if not missing:
                raise RuntimeError(f"IndexTTS-2.5 worker failed to load: {error_text}")
            attempted |= missing
            if not _pip_install_into_indextts_env(missing):
                raise RuntimeError(f"IndexTTS-2.5 worker failed to load: {error_text}")
            console.print("[dim]Retrying IndexTTS-2.5 worker startup with the newly installed package(s)...[/]")

        raise RuntimeError(f"IndexTTS-2.5 worker still fails to load after installing: {', '.join(sorted(attempted))}")

    def _get_emotion_vector(self, emotion_tag: str) -> List[float]:
        """
        Always returns a flat 8-dimensional zero vector [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0].
        This completely eliminates emotional fluctuations, screams, shock spikes, and vocal strain,
        ensuring uniform, objective, and consistent documentary-style narration across all panels.
        """
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def _adjust_audio_speed(self, wav_path: Path, speed: float) -> None:
        """Adjusts speaking tempo using pitch-preserving FFmpeg atempo filter."""
        if abs(speed - 1.0) < 0.02 or not wav_path.exists():
            return
        temp_wav = wav_path.with_name(f"{wav_path.stem}_speedtmp.wav")
        wav_path.rename(temp_wav)
        tempo = max(0.5, min(2.0, speed))
        cmd = [
            "ffmpeg", "-y",
            "-i", str(temp_wav),
            "-filter:a", f"atempo={tempo}",
            "-ar", str(self.audio_config.sample_rate),
            str(wav_path)
        ]
        try:
            run_ffmpeg(cmd, check=True)
            if temp_wav.exists():
                temp_wav.unlink()
        except Exception:
            if temp_wav.exists() and not wav_path.exists():
                temp_wav.rename(wav_path)

    def synthesize(self, text: str, emotion_tag: str, spk_prompt_path: str, output_wav: Path) -> None:
        """Synthesizes speech via the IndexTTS-2.5 worker process. Uses a flat
        zero emotion vector and low temperature/top_p for consistent delivery."""
        proc = self._ensure_worker()

        request = {
            "cmd": "synthesize",
            "spk_audio_prompt": spk_prompt_path,
            "text": text,
            "lang": (self.tts_config.lang or "EN").strip().upper(),
            "output_path": str(output_wav.resolve()),
            "emo_vector": self._get_emotion_vector(emotion_tag),
            "temperature": self.tts_config.temperature,
            "top_p": self.tts_config.top_p,
        }
        if abs(self.tts_config.speed - 1.0) >= 0.02:
            request["duration_factor"] = round(1.0 / self.tts_config.speed, 3)

        try:
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = proc.stdout.readline()
        except (BrokenPipeError, OSError) as e:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"IndexTTS-2.5 worker died mid-synthesis: {e}\n{stderr}") from e

        if not response_line:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"IndexTTS-2.5 worker closed its output unexpectedly:\n{stderr}")

        response = json.loads(response_line)
        if not response.get("ok"):
            raise RuntimeError(f"IndexTTS-2.5 synthesis failed: {response.get('error')}")

        # duration_factor already handles speed on the model side when supported;
        # only fall back to the ffmpeg post-process if the worker couldn't use it
        # (older IndexTTS checkouts without a duration_factor parameter).
        if "duration_factor" not in request and abs(self.tts_config.speed - 1.0) >= 0.02:
            self._adjust_audio_speed(output_wav, self.tts_config.speed)

    def shutdown(self) -> None:
        """Cleanly stops the worker process, if one is running. Safe to call
        multiple times; also registered via atexit as a safety net."""
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
            proc.stdin.flush()
            proc.wait(timeout=5)
        except Exception:
            proc.terminate()
