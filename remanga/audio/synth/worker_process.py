"""The worker process under every TTS engine: spawning it, waiting for its
ready handshake, auto-healing a dependency its own install didn't pin,
bounded reads of its replies, draining its stderr so it can't deadlock on a
full pipe, and shutting it down cleanly. Mixed into BaseWorkerSynthesizer
(base.py), which adds the synthesis requests themselves."""

from __future__ import annotations

import collections
import json
import select
import subprocess
import threading

from remanga.console import console
from remanga.paths import UV_BIN
from remanga.venvs import extract_missing_packages, get_tool_python

_MAX_AUTO_HEAL_ATTEMPTS = 8

# How many of the worker's most recent stderr lines to keep around for error
# messages (see _drain_stderr). Everything older just gets dropped.
STDERR_TAIL_LINES = 200


def _pip_install_into_tool_env(tool_name: str, packages: set) -> bool:
    """Installs `packages` into `.tools/venv-<tool_name>`, preferring this
    repo's own `bin/uv` (that isolated venv has no `pip` module at all)."""
    names = sorted(packages)
    console.print(f"[yellow]Installing missing dependency into .tools/venv-{tool_name}: {' '.join(names)}...[/]")

    uv_bin = UV_BIN
    python = get_tool_python(tool_name)
    cmd = [str(uv_bin), "pip", "install", "--python", str(python), *names] if uv_bin.exists() \
        else [str(python), "-m", "pip", "install", *names]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        console.print(f"[bold red]Failed to install {' '.join(names)} automatically.[/]")
        return False
    console.print(f"[bold green]✓ Installed {' '.join(names)}.[/]")
    return True


class WorkerProcessMixin:
    """The worker's lifecycle, for BaseWorkerSynthesizer. Uses the
    synthesizer's `tool_name`, `display_name`, `model_manager` and
    `_spawn_worker()`, and keeps the process in `_proc`, `_stderr_tail` and
    `_stderr_thread`."""

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        """Runs for the lifetime of one worker process, on its own daemon
        thread, continuously reading its stderr so the pipe can never fill
        up and block the worker's next write to it - see kokoro_worker.py's
        module docstring for the deadlock this specifically prevents. Only
        the last STDERR_TAIL_LINES lines are kept, for error messages;
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
                self._stderr_tail = collections.deque(maxlen=STDERR_TAIL_LINES)
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

        raise RuntimeError(
            f"{self.display_name} worker still fails to load after installing: {', '.join(sorted(attempted))}"
        )

    def ensure_ready(self) -> None:
        """Loads the model weights and spawns the worker if that hasn't happened yet.
        Callers that are about to open their own Rich Live display (a Progress bar,
        a `console.status()` spinner) should call this first and let it finish -
        `ensure_model()`/`_ensure_worker()` open their own status spinner while
        loading, and two Live displays racing to redraw the same terminal lines at
        once is exactly what produces stacked/garbled progress output."""
        self._ensure_worker()

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
            # Ctrl+C (see cli.py's KeyboardInterrupt handling), and a *second*
            # Ctrl+C landing while proc.wait() above is blocked raises
            # KeyboardInterrupt right here - a plain `except Exception` doesn't
            # catch that, so proc.terminate() below would never run and the
            # worker (GPU memory and all) would be orphaned instead of
            # killed. Swallow it here (we're already tearing down) rather
            # than re-raising into "Exception ignored in atexit callback".
            proc.terminate()
