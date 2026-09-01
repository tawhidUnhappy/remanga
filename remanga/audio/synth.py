"""Low-level speech synthesis, one class per supported TTS engine
(TTSConfig.engine - see remanga/config.py's TTS_ENGINES), each spawning and
talking to its own isolated `.tools/venv-<tool>` worker process
(remanga/audio/scripts/*_worker.py) so no two engines' dependency pins ever
have to share a Python process or a dependency resolution with each other or
with MAGI v3's isolated environment. See remanga/venvs.py for how those
environments are located.

Both synthesizer classes share the exact same worker-process lifecycle
(spawn, ready-handshake, auto-heal a missing dependency, bounded-timeout
request/response, stderr draining so a wedged worker can't deadlock, clean
shutdown) via `_BaseWorkerSynthesizer` below - only the process command line
and the per-request JSON payload actually differ per engine. Adding a third
engine later means subclassing that base, not re-implementing all of this."""

from __future__ import annotations

import atexit
import collections
import json
import select
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from remanga.config import AudioConfig, TTSConfig
from remanga.console import console
from remanga.ffmpeg_io import run_ffmpeg
from remanga.models import ModelManager
from remanga.setup import read_reference_text
from remanga.venvs import REPO_ROOT, extract_missing_packages, get_scripts_dir, get_tool_python

_MAX_AUTO_HEAL_ATTEMPTS = 8

# How many of the worker's most recent stderr lines to keep around for error
# messages (see _drain_stderr). Everything older just gets dropped.
_STDERR_TAIL_LINES = 200


def _pip_install_into_tool_env(tool_name: str, packages: set) -> bool:
    """Installs `packages` into `.tools/venv-<tool_name>`, preferring this
    repo's own `bin/uv` (that isolated venv has no `pip` module at all)."""
    names = sorted(packages)
    console.print(f"[yellow]Installing missing dependency into .tools/venv-{tool_name}: {' '.join(names)}...[/]")

    uv_bin = REPO_ROOT / "bin" / "uv"
    python = get_tool_python(tool_name)
    cmd = [str(uv_bin), "pip", "install", "--python", str(python), *names] if uv_bin.exists() \
        else [str(python), "-m", "pip", "install", *names]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"[bold red]Failed to install {' '.join(names)} automatically.[/]")
        return False
    console.print(f"[bold green]✓ Installed {' '.join(names)}.[/]")
    return True


class _BaseWorkerSynthesizer:
    """Owns one long-lived isolated-venv worker subprocess and speaks to it
    over stdin/stdout for every synthesize() call, so the model loads onto
    the GPU once per production run instead of once per panel. Subclasses
    fill in: `tool_name` (selects `.tools/venv-<tool_name>`), `display_name`
    (for console messages), `_spawn_worker()` (the process command line),
    and `_build_request()` (the per-call JSON payload)."""

    tool_name: str = ""
    display_name: str = ""

    def __init__(self, audio_config: AudioConfig, model_manager: ModelManager):
        self.audio_config = audio_config
        self.model_manager = model_manager
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_tail: collections.deque = collections.deque(maxlen=_STDERR_TAIL_LINES)
        self._stderr_thread: Optional[threading.Thread] = None
        atexit.register(self.shutdown)

    # --- subclass hooks -----------------------------------------------
    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        raise NotImplementedError

    def _build_request(self, text: str, spk_prompt_path: str, output_wav: Path) -> Dict[str, Any]:
        raise NotImplementedError

    def _synth_timeout_seconds(self) -> float:
        raise NotImplementedError

    def _post_synthesize(self, output_wav: Path, request: Dict[str, Any]) -> None:
        """Optional per-engine post-processing after a successful synthesis
        (e.g. IndexTTS's ffmpeg-atempo speed fallback). No-op by default."""

    # --- shared worker-process machinery -------------------------------
    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        """Runs for the lifetime of one worker process, on its own daemon
        thread, continuously reading its stderr so the pipe can never fill
        up and block the worker's next write to it - see indextts_worker.py's
        module docstring for the deadlock this specifically prevents. Only
        the last _STDERR_TAIL_LINES lines are kept, for error messages;
        everything older is simply dropped."""
        try:
            for line in proc.stderr:
                self._stderr_tail.append(line)
        except (ValueError, OSError):
            pass  # pipe closed under us (worker exited) - nothing left to drain

    def _stderr_snapshot(self) -> str:
        return "".join(self._stderr_tail)

    def _ensure_worker(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc

        model_dir = self.model_manager.ensure_model()
        console.print(f"[cyan]Starting {self.display_name} worker...[/]")

        # Auto-heal: a missing dependency the engine's own install didn't pin
        # gets installed into its isolated venv and retried, instead of
        # raising mid-session over something one pip install would have
        # fixed. See remanga/webui/magi_assist.py for the same pattern
        # against MAGI v3's own isolated env.
        attempted: set = set()
        for _ in range(_MAX_AUTO_HEAL_ATTEMPTS + 1):
            proc = self._spawn_worker(model_dir)
            ready_line = proc.stdout.readline()
            if not ready_line:
                stderr = proc.stderr.read()
                raise RuntimeError(f"{self.display_name} worker exited before starting up:\n{stderr}")

            event = json.loads(ready_line)
            if event.get("event") == "ready":
                console.print(f"[bold green]✓ {self.display_name} worker ready.[/]")
                self._proc = proc
                self._stderr_tail = collections.deque(maxlen=_STDERR_TAIL_LINES)
                self._stderr_thread = threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True)
                self._stderr_thread.start()
                return proc

            error_text = event.get("error", "")
            missing = extract_missing_packages(error_text) - attempted
            if not missing:
                raise RuntimeError(f"{self.display_name} worker failed to load: {error_text}")
            attempted |= missing
            if not _pip_install_into_tool_env(self.tool_name, missing):
                raise RuntimeError(f"{self.display_name} worker failed to load: {error_text}")
            console.print(f"[dim]Retrying {self.display_name} worker startup with the newly installed package(s)...[/]")

        raise RuntimeError(f"{self.display_name} worker still fails to load after installing: {', '.join(sorted(attempted))}")

    def ensure_ready(self) -> None:
        """Loads the model weights and spawns the worker if that hasn't happened yet.
        Callers that are about to open their own Rich Live display (a Progress bar,
        a `console.status()` spinner) should call this first and let it finish -
        `ensure_model()`/`_ensure_worker()` open their own status spinner while
        loading, and two Live displays racing to redraw the same terminal lines at
        once is exactly what produces stacked/garbled progress output."""
        self._ensure_worker()

    def _adjust_audio_speed(self, wav_path: Path, speed: float) -> None:
        """Adjusts speaking tempo using pitch-preserving FFmpeg atempo filter -
        the fallback path for an engine/request that couldn't apply speed on
        the model side itself."""
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

    def synthesize(self, text: str, spk_prompt_path: str, output_wav: Path) -> None:
        """Synthesizes speech via this engine's worker process."""
        proc = self._ensure_worker()
        request = self._build_request(text, spk_prompt_path, output_wav)

        try:
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = self._read_response_line(proc, self._synth_timeout_seconds())
        except TimeoutError as e:
            stderr = self._stderr_snapshot()
            self._kill_stuck_worker(proc)
            raise RuntimeError(
                f"{self.display_name} worker {e} on panel text {text[:80]!r} - killed it so the next attempt "
                f"gets a fresh one. Safe to just re-run; already-synthesized panels are cached and this "
                f"one regenerates automatically.\n{stderr}"
            ) from e
        except (BrokenPipeError, OSError) as e:
            stderr = self._stderr_snapshot()
            raise RuntimeError(f"{self.display_name} worker died mid-synthesis: {e}\n{stderr}") from e

        if not response_line:
            stderr = self._stderr_snapshot()
            raise RuntimeError(f"{self.display_name} worker closed its output unexpectedly:\n{stderr}")

        response = json.loads(response_line)
        if not response.get("ok"):
            raise RuntimeError(f"{self.display_name} synthesis failed: {response.get('error')}")

        self._post_synthesize(output_wav, request)

    def shutdown(self) -> None:
        """Cleanly stops the worker process, if one is running. Safe to call
        multiple times; also registered via atexit as a safety net."""
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        console.print(f"[dim]Stopping {self.display_name} worker...[/]")
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


class IndexTTSSynthesizer(_BaseWorkerSynthesizer):
    """IndexTTS-2.5 - talks to `.tools/venv-indextts`/indextts_worker.py."""

    tool_name = "indextts"
    display_name = "IndexTTS-2.5"

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        super().__init__(audio_config, ModelManager(
            tts_config.model_dir, tts_config.hf_repo_id,
            tool_name="indextts", download_script="download_indextts.py",
            expected_files=("gpt.pth", "s2mel.pth"), display_name="IndexTTS-2.5",
        ))

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

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, spk_prompt_path: str, output_wav: Path) -> Dict[str, Any]:
        """Deliberately sends no emo_vector: IndexTTS-2.5 infers its own
        emotion/prosody straight from `text`'s own wording and punctuation
        ("!"/"?"/"..." etc - see prompts/narration.md Rule 3) when none is
        supplied, which is what makes narration sound naturally expressive
        instead of a forced-flat reading of whatever the text actually
        says. Temperature/top_p (TTSConfig) are left at IndexTTS-2.5's own
        recommended defaults for natural prosody within that inferred
        emotion."""
        request: Dict[str, Any] = {
            "cmd": "synthesize",
            "spk_audio_prompt": spk_prompt_path,
            "text": text,
            "lang": (self.tts_config.lang or "EN").strip().upper(),
            "output_path": str(output_wav.resolve()),
            "temperature": self.tts_config.temperature,
            "top_p": self.tts_config.top_p,
        }
        if abs(self.tts_config.speed - 1.0) >= 0.02:
            request["duration_factor"] = round(1.0 / self.tts_config.speed, 3)
        return request

    def _post_synthesize(self, output_wav: Path, request: Dict[str, Any]) -> None:
        # duration_factor already handles speed on the model side when supported;
        # only fall back to the ffmpeg post-process if the worker couldn't use it
        # (older IndexTTS checkouts without a duration_factor parameter).
        if "duration_factor" not in request and abs(self.tts_config.speed - 1.0) >= 0.02:
            self._adjust_audio_speed(output_wav, self.tts_config.speed)


class Audio8Synthesizer(_BaseWorkerSynthesizer):
    """Audio8/Audio8-TTS-Preview-0.1b - talks to `.tools/venv-audio8`/
    audio8_worker.py. See config.Audio8Config for its settings and
    audio8_worker.py's module docstring for the model itself."""

    tool_name = "audio8"
    display_name = "Audio8 TTS"

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.audio8
        super().__init__(audio_config, ModelManager(
            self.engine_config.model_dir, self.engine_config.hf_repo_id,
            tool_name="audio8", download_script="download_audio8.py",
            expected_files=("model.safetensors", "codec.pth"), display_name="Audio8 TTS",
        ))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        python = get_tool_python("audio8")
        script = get_scripts_dir("audio") / "audio8_worker.py"

        cmd: List[str] = [
            str(python), "-u", str(script),
            "--model_dir", str(model_dir.resolve()),
        ]
        if self.engine_config.use_bf16:
            cmd.append("--use_bf16")

        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, spk_prompt_path: str, output_wav: Path) -> Dict[str, Any]:
        # Read fresh each call rather than caching at __init__ - the file is
        # small, this runs once per panel not per token, and it means an
        # edit to the transcript file takes effect on the very next panel
        # without restarting the pipeline.
        return {
            "cmd": "synthesize",
            "spk_audio_prompt": spk_prompt_path,
            "reference_text": read_reference_text(self.engine_config.reference_text_path),
            "text": text,
            "output_path": str(output_wav.resolve()),
            "temperature": self.engine_config.temperature,
            "top_p": self.engine_config.top_p,
            "max_new_tokens": self.engine_config.max_new_tokens,
        }

    def _post_synthesize(self, output_wav: Path, request: Dict[str, Any]) -> None:
        # No model-side speed control for this engine - fall back to the
        # shared ffmpeg-atempo path whenever tts.speed isn't 1.0.
        if abs(self.tts_config.speed - 1.0) >= 0.02:
            self._adjust_audio_speed(output_wav, self.tts_config.speed)


def create_synthesizer(tts_config: TTSConfig, audio_config: AudioConfig) -> _BaseWorkerSynthesizer:
    """Picks the Synthesizer matching `tts_config.engine` (see
    config.TTS_ENGINES) - the one place that mapping is made, so callers
    (audio/tts.py) never need to know about individual engine classes."""
    engine = (tts_config.engine or "indextts-2.5").strip().lower()
    if engine == "audio8-tts-0.1b":
        return Audio8Synthesizer(tts_config, audio_config)
    if engine != "indextts-2.5":
        console.print(f"[yellow]Unknown tts.engine {engine!r} - falling back to indextts-2.5.[/]")
    return IndexTTSSynthesizer(tts_config, audio_config)
