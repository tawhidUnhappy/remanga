"""Low-level IndexTTS-2.5 speech synthesis: spawns and talks to the isolated
`.venv-indextts` worker process (remanga/audio/scripts/indextts_worker.py) so
IndexTTS's own dependency pins never have to share a Python process - or a
dependency resolution - with the rest of remanga or with MAGI v3's isolated
environment. See remanga/venvs.py for how that environment is located."""

from __future__ import annotations

import atexit
import collections
import json
import select
import subprocess
import threading
from pathlib import Path
from typing import List, Optional
from pydub import AudioSegment

from remanga.config import AudioConfig, TTSConfig
from remanga.console import console
from remanga.ffmpeg_io import run_ffmpeg
from remanga.models import ModelManager
from remanga.venvs import REPO_ROOT, extract_missing_packages, get_scripts_dir, get_tool_python

_MAX_AUTO_HEAL_ATTEMPTS = 8

# How many of the worker's most recent stderr lines to keep around for error
# messages (see _drain_stderr). Everything older just gets dropped.
_STDERR_TAIL_LINES = 200


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
        self._stderr_tail: collections.deque = collections.deque(maxlen=_STDERR_TAIL_LINES)
        self._stderr_thread: Optional[threading.Thread] = None
        atexit.register(self.shutdown)

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        """Runs for the lifetime of one worker process, on its own daemon thread,
        continuously reading its stderr so the pipe can never fill up and block
        the worker's next write to it.

        Why this exists: indextts_worker.py only redirects the model's *stdout*
        (IndexTTS2.infer() prints straight to it - see that script's own
        comment); anything written to stderr instead - a tqdm progress bar, a
        warnings.warn(), a logging handler someone set up against sys.stderr -
        goes straight into this pipe untouched. Nothing used to read it during
        normal operation, only on an error path via a one-shot proc.stderr.read()
        - so once enough of that accumulated past the OS pipe's buffer (64KB on
        Linux), the worker's next write to stderr simply blocked: the whole
        process sat there mid-write, GPU memory still held, model still loaded,
        zero forward progress, while this side waited on a stdout response line
        that was never coming because the worker never got back from that
        write() call. ("Stuck at 42/135, GPU memory loaded but doing nothing.")

        Only the last _STDERR_TAIL_LINES lines are kept, for error messages;
        everything older is simply dropped - unlike a one-shot read, this never
        lets the pipe back up in the first place.
        """
        try:
            for line in proc.stderr:
                self._stderr_tail.append(line)
        except (ValueError, OSError):
            pass  # pipe closed under us (worker exited) - nothing left to drain

    def _stderr_snapshot(self) -> str:
        return "".join(self._stderr_tail)

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
                self._stderr_tail = collections.deque(maxlen=_STDERR_TAIL_LINES)
                self._stderr_thread = threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True)
                self._stderr_thread.start()
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

    def ensure_ready(self) -> None:
        """Loads the model weights and spawns the worker if that hasn't happened yet.
        Callers that are about to open their own Rich Live display (a Progress bar,
        a `console.status()` spinner) should call this first and let it finish -
        `ensure_model()`/`_ensure_worker()` open their own status spinner while
        loading, and two Live displays racing to redraw the same terminal lines at
        once is exactly what produces stacked/garbled progress output."""
        self._ensure_worker()

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

    def _read_response_line(self, proc: subprocess.Popen, timeout: float) -> str:
        """proc.stdout.readline(), but bounded: select() waits up to `timeout`
        seconds for the pipe to actually have data before ever calling
        readline(), which would otherwise block indefinitely. That turns a
        wedged worker - the stderr-pipe deadlock _drain_stderr() exists to
        prevent, or anything else that makes a single panel never come back -
        into a clear, bounded error instead of an indefinite hang."""
        ready, _, _ = select.select([proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(f"didn't respond within {timeout:.0f}s")
        return proc.stdout.readline()

    def _kill_stuck_worker(self, proc: subprocess.Popen) -> None:
        """Forcibly kills a worker that's stopped responding and forgets it, so
        the next synthesize() call spawns (and reloads the model into) a fresh
        one instead of trying to talk to the same wedged process again."""
        if self._proc is proc:
            self._proc = None
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass

    def synthesize(self, text: str, emotion_tag: str, spk_prompt_path: str, output_wav: Path) -> None:
        """Synthesizes speech via the IndexTTS-2.5 worker process. Uses a flat
        zero emotion vector for consistent narration tone, with IndexTTS-2.5's
        own recommended temperature/top_p (TTSConfig) for natural prosody."""
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
            response_line = self._read_response_line(proc, self.tts_config.synth_timeout_seconds)
        except TimeoutError as e:
            stderr = self._stderr_snapshot()
            self._kill_stuck_worker(proc)
            raise RuntimeError(
                f"IndexTTS-2.5 worker {e} on panel text {text[:80]!r} - killed it so the next attempt "
                f"gets a fresh one. Safe to just re-run; already-synthesized panels are cached and this "
                f"one regenerates automatically.\n{stderr}"
            ) from e
        except (BrokenPipeError, OSError) as e:
            stderr = self._stderr_snapshot()
            raise RuntimeError(f"IndexTTS-2.5 worker died mid-synthesis: {e}\n{stderr}") from e

        if not response_line:
            stderr = self._stderr_snapshot()
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
        console.print("[dim]Stopping IndexTTS-2.5 worker...[/]")
        try:
            proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
            proc.stdin.flush()
            proc.wait(timeout=5)
        except BaseException:
            # BaseException, not Exception: this runs from atexit after a
            # Ctrl+C (see cli.py's graceful_sigint_handler), and a *second*
            # Ctrl+C landing while proc.wait() above is blocked raises
            # SystemExit right here - a plain `except Exception` doesn't
            # catch that, so proc.terminate() below would never run and the
            # worker (GPU memory and all) would be orphaned instead of
            # killed. Swallow it here (we're already tearing down) rather
            # than re-raising into "Exception ignored in atexit callback".
            proc.terminate()
