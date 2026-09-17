"""One long-lived worker subprocess, and the conversation with it.

A heavy engine - Chatterbox synthesizing a page - loads its model once and then answers requests over
stdin/stdout, so that cost is paid per session instead of per page. This is
the side of that conversation remanga owns: spawning the process (heal.py
handles a dependency its install missed), draining its stderr so a full pipe
can't deadlock it, bounded reads so a wedged worker fails clearly instead of
hanging, and a clean shutdown.

Mixed into the engine's class (audio/synth/base.py),
which adds only what differs between them: the command line, the request
payload, and what to do with the answer."""

from __future__ import annotations

import atexit
import collections
import json
import select
import subprocess
import threading
from pathlib import Path

from remanga.console import console
from remanga.venvs import get_scripts_dir, get_tool_python
from remanga.workers.heal import start_worker

# How many of the worker's most recent stderr lines to keep for error
# messages (see _drain_stderr). Everything older is simply dropped.
STDERR_TAIL_LINES = 200


def spawn_script_worker(tool_name: str, package_relpath: str, script_name: str, *args: str) -> subprocess.Popen:
    """The standard worker process: a tool's own interpreter running one of
    that package's scripts/, line-buffered text pipes on all three streams.
    `get_tool_python` provisions the environment if this is its first use."""
    python = get_tool_python(tool_name)
    script = get_scripts_dir(package_relpath) / script_name
    return subprocess.Popen(
        [str(python), "-u", str(script), *args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
    )


class ToolWorker:
    """The worker lifecycle, mixed into an engine's own class.

    A subclass sets `tool_name` (which `.tools/venv-<name>` to run in) and
    `display_name` (what console messages call it), fills in
    `_spawn_worker()`, calls `_init_worker_state()` from its __init__, and
    carries a `model_manager` whose `ensure_model()` returns the weights
    directory. `_on_ready()` and `starting_note` are for an engine with
    something of its own to say while loading."""

    tool_name: str = ""
    display_name: str = ""
    # Appended to "Starting <display name> worker" - e.g. " (prefers GPU,
    # falls back to CPU)" for an engine that may land on either.
    starting_note: str = ""

    def _init_worker_state(self) -> None:
        """The process bookkeeping every worker starts with. Called from the
        engine's own __init__ rather than an __init__ here, so a subclass
        keeps whatever constructor signature suits it."""
        self._proc: subprocess.Popen | None = None
        self._stderr_tail: collections.deque = collections.deque(maxlen=STDERR_TAIL_LINES)
        self._stderr_thread: threading.Thread | None = None
        atexit.register(self.shutdown)

    # --- subclass hooks -------------------------------------------------
    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        raise NotImplementedError

    def _on_ready(self, event: dict) -> None:
        """Announce the worker, and keep whatever its ready event says about
        itself. The default just says it is ready."""
        console.print(f"[bold green]✓ {self.display_name} worker ready.[/]")

    # --- the process ----------------------------------------------------
    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        """Runs for the lifetime of one worker process, on its own daemon
        thread, continuously reading its stderr so the pipe can never fill
        up and block the worker's next write to it - see chatterbox_worker.py's
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
        console.print(f"[cyan]Starting {self.display_name} worker{self.starting_note}...[/]")
        proc, event = start_worker(
            lambda: self._spawn_worker(model_dir), display_name=self.display_name, tool_name=self.tool_name,
        )
        self._proc = proc
        self._stderr_tail = collections.deque(maxlen=STDERR_TAIL_LINES)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True)
        self._stderr_thread.start()
        self._on_ready(event)
        return proc

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
        prevent, or anything else that makes a single request never come back -
        into a clear, bounded error instead of an indefinite hang."""
        ready, _, _ = select.select([proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(f"didn't respond within {timeout:.0f}s")
        return proc.stdout.readline()

    def _kill_stuck_worker(self, proc: subprocess.Popen) -> None:
        """Forcibly kills a worker that's stopped responding and forgets it, so
        the next request spawns (and reloads the model into) a fresh one
        instead of trying to talk to the same wedged process again."""
        if self._proc is proc:
            self._proc = None
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass

    def _request(self, payload: dict, timeout: float, *, action: str,
                 on_timeout: str = "", advice: str = "") -> dict:
        """One request to the worker, start to finish: the answer as a dict,
        or a RuntimeError naming what went wrong - a timeout (the worker is
        killed, so the next request gets a fresh one), a process that died
        mid-request, one that closed its output, or a refusal.

        `action` is the word the messages use for what was being asked for
        ("synthesis", "recognition"); `on_timeout` and `advice` let an engine
        add what this particular request was and what to do about it."""
        proc = self._ensure_worker()

        try:
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            response_line = self._read_response_line(proc, timeout)
        except TimeoutError as e:
            stderr = self._stderr_snapshot()
            self._kill_stuck_worker(proc)
            raise RuntimeError(
                f"{self.display_name} worker {e}{on_timeout} - killed it so the next attempt "
                f"gets a fresh one.{advice}\n{stderr}"
            ) from e
        except (BrokenPipeError, OSError) as e:
            stderr = self._stderr_snapshot()
            raise RuntimeError(f"{self.display_name} worker died mid-{action}: {e}\n{stderr}") from e

        if not response_line:
            stderr = self._stderr_snapshot()
            raise RuntimeError(f"{self.display_name} worker closed its output unexpectedly:\n{stderr}")

        response = json.loads(response_line)
        if not response.get("ok"):
            raise RuntimeError(f"{self.display_name} {action} failed: {response.get('error')}")
        return response

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
