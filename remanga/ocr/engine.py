"""OCREngine: owns one long-lived `.tools/venv-lighton-ocr` worker subprocess
(remanga/ocr/scripts/lighton_ocr_worker.py), spoken to over stdin/stdout so
LightOnOCR-2 loads onto the GPU once per Narration Writer session instead
of once per "OCR this panel" click. Mirrors remanga/audio/synth/'s
_BaseWorkerSynthesizer lifecycle (spawn, ready-handshake, auto-heal a missing
dependency, bounded-timeout request/response, stderr draining so a wedged
worker can't deadlock, clean shutdown) - written standalone rather than
subclassing that base, since its interface (voice/output_wav) is TTS-specific
and OCR has exactly one engine, not several sharing a base."""

from __future__ import annotations

import atexit
import collections
import json
import select
import subprocess
import threading
from pathlib import Path

from remanga.config import OCRConfig
from remanga.console import console
from remanga.models.weights import ModelManager
from remanga.ocr.cleanup import clean_ocr_text
from remanga.paths import UV_BIN
from remanga.venvs import extract_missing_packages, get_scripts_dir, get_tool_python

_MAX_AUTO_HEAL_ATTEMPTS = 8
_STDERR_TAIL_LINES = 200
# Generous but bounded, same reasoning as TTSConfig's own
# synth_timeout_seconds: a wedged worker should fail clearly, not hang the
# Narration Writer UI's request forever. A 1B model reading one panel is
# well inside this on a GPU; CPU is far slower, which is what the ceiling
# is sized for.
_RECOGNIZE_TIMEOUT_SECONDS = 120.0

TOOL_NAME = "lighton-ocr"
DISPLAY_NAME = "LightOnOCR-2"


def _pip_install_into_tool_env(packages: set) -> bool:
    names = sorted(packages)
    console.print(f"[yellow]Installing missing dependency into .tools/venv-{TOOL_NAME}: {' '.join(names)}...[/]")
    python = get_tool_python(TOOL_NAME)
    cmd = [str(UV_BIN), "pip", "install", "--python", str(python), *names] if UV_BIN.exists() \
        else [str(python), "-m", "pip", "install", *names]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"[bold red]Failed to install {' '.join(names)} automatically.[/]")
        return False
    console.print(f"[bold green]✓ Installed {' '.join(names)}.[/]")
    return True


class OCREngine:
    """One instance per Narration Writer session (see writer_state.py) -
    lazily spawns its worker (and, before that, downloads the model weights
    if they aren't already present - same lazy-fetch-on-first-use pattern
    every TTS engine already follows) on the *first* recognize() call, so
    opening the Narration Writer never pays GPU/model-load cost unless the
    user actually clicks "OCR this panel"."""

    def __init__(self, ocr_config: OCRConfig):
        self.ocr_config = ocr_config
        self.model_manager = ModelManager(
            ocr_config.model_dir, ocr_config.hf_repo_id,
            tool_name=TOOL_NAME, download_script="download_lighton_ocr.py",
            expected_files=("config.json", "model.safetensors"), display_name=DISPLAY_NAME,
        )
        self._proc: subprocess.Popen | None = None
        self._stderr_tail: collections.deque = collections.deque(maxlen=_STDERR_TAIL_LINES)
        self._stderr_thread: threading.Thread | None = None
        self.device: str | None = None
        atexit.register(self.shutdown)

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stderr:
                self._stderr_tail.append(line)
        except (ValueError, OSError):
            pass  # pipe closed under us (worker exited) - nothing left to drain

    def _stderr_snapshot(self) -> str:
        return "".join(self._stderr_tail)

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        python = get_tool_python(TOOL_NAME)
        script = get_scripts_dir("ocr") / "lighton_ocr_worker.py"
        return subprocess.Popen(
            [str(python), "-u", str(script), str(model_dir.resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _ensure_worker(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc

        model_dir = self.model_manager.ensure_model()
        console.print(f"[cyan]Starting {DISPLAY_NAME} worker (prefers GPU, falls back to CPU)...[/]")

        attempted: set = set()
        for _ in range(_MAX_AUTO_HEAL_ATTEMPTS + 1):
            proc = self._spawn_worker(model_dir)
            ready_line = proc.stdout.readline()
            if not ready_line:
                stderr = proc.stderr.read()
                raise RuntimeError(f"{DISPLAY_NAME} worker exited before starting up:\n{stderr}")

            event = json.loads(ready_line)
            if event.get("event") == "ready":
                self.device = event.get("device")
                console.print(
                    f"[bold green]✓ {DISPLAY_NAME} worker ready[/] "
                    f"[dim]({'GPU' if self.device == 'cuda' else 'CPU - no GPU available'})[/]"
                )
                self._proc = proc
                self._stderr_tail = collections.deque(maxlen=_STDERR_TAIL_LINES)
                self._stderr_thread = threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True)
                self._stderr_thread.start()
                return proc

            error_text = event.get("error", "")
            missing = extract_missing_packages(error_text) - attempted
            if not missing:
                raise RuntimeError(f"{DISPLAY_NAME} worker failed to load: {error_text}")
            attempted |= missing
            if not _pip_install_into_tool_env(missing):
                raise RuntimeError(f"{DISPLAY_NAME} worker failed to load: {error_text}")
            console.print(f"[dim]Retrying {DISPLAY_NAME} worker startup with the newly installed package(s)...[/]")

        raise RuntimeError(
            f"{DISPLAY_NAME} worker still fails to load after installing: {', '.join(sorted(attempted))}"
        )

    def _read_response_line(self, proc: subprocess.Popen, timeout: float) -> str:
        ready, _, _ = select.select([proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(f"didn't respond within {timeout:.0f}s")
        return proc.stdout.readline()

    def _kill_stuck_worker(self, proc: subprocess.Popen) -> None:
        if self._proc is proc:
            self._proc = None
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass

    def recognize(self, image_path: Path, prompt: str | None = None) -> str:
        """Runs OCR on one panel image, returning the recognized text (empty
        string if the model found none). Raises RuntimeError on a worker
        failure/timeout - the caller (writer_routes.py) turns that into an
        HTTP error the frontend surfaces, not a crash."""
        proc = self._ensure_worker()
        request = {
            "cmd": "recognize",
            "image_path": str(Path(image_path).resolve()),
            "max_new_tokens": self.ocr_config.max_new_tokens,
        }
        # An explicit argument wins over the configured default, and an empty
        # prompt is sent as nothing at all rather than as an empty text turn -
        # see the worker for why those are not the same to the chat template.
        chosen = prompt if prompt is not None else self.ocr_config.prompt
        if chosen:
            request["prompt"] = chosen

        try:
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            response_line = self._read_response_line(proc, _RECOGNIZE_TIMEOUT_SECONDS)
        except TimeoutError as e:
            stderr = self._stderr_snapshot()
            self._kill_stuck_worker(proc)
            raise RuntimeError(
                f"{DISPLAY_NAME} worker {e} - killed it so the next attempt gets a fresh one.\n{stderr}"
            ) from e
        except (BrokenPipeError, OSError) as e:
            stderr = self._stderr_snapshot()
            raise RuntimeError(f"{DISPLAY_NAME} worker died mid-recognition: {e}\n{stderr}") from e

        if not response_line:
            stderr = self._stderr_snapshot()
            raise RuntimeError(f"{DISPLAY_NAME} worker closed its output unexpectedly:\n{stderr}")

        response = json.loads(response_line)
        if not response.get("ok"):
            raise RuntimeError(f"{DISPLAY_NAME} recognition failed: {response.get('error')}")
        # Cleaned here rather than in the worker: the worker is meant to be a
        # thin, dependency-free shell around the model, and this is a
        # judgement about output quality that belongs where it can be read and
        # changed without touching the isolated environment. See ocr/cleanup.py
        # for why the model needs it at all.
        return clean_ocr_text(response.get("text", ""))

    def shutdown(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        console.print(f"[dim]Stopping {DISPLAY_NAME} worker...[/]")
        try:
            proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
            proc.stdin.flush()
            proc.wait(timeout=5)
        except BaseException:
            # BaseException, not Exception - see _BaseWorkerSynthesizer.shutdown()
            # in audio/synth/base.py for why (a second Ctrl+C landing mid-wait here
            # must still reach proc.terminate() instead of orphaning the worker).
            proc.terminate()
