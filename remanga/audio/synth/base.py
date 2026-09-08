"""The worker-process machinery every TTS engine shares.

One class owns the whole lifecycle of an isolated-venv worker: spawn it,
wait for its ready handshake, auto-heal a dependency its own install
didn't pin, send bounded-timeout requests, drain its stderr so it can't
deadlock on a full pipe, and shut it down cleanly. An engine subclass fills
in only what actually differs between engines - the command line and the
per-request payload - which is what keeps adding a third engine to a small
file (see kokoro.py, under 80 lines) rather than a
fourth copy of all of this."""

from __future__ import annotations

import atexit
import collections
import json
import re
import select
import subprocess
import threading
from pathlib import Path
from typing import Any

from remanga.config import AudioConfig
from remanga.console import console
from remanga.ffmpeg_io import run_ffmpeg
from remanga.models import ModelManager
from remanga.paths import UV_BIN
from remanga.venvs import extract_missing_packages, get_tool_python

_MAX_AUTO_HEAL_ATTEMPTS = 8

# How many of the worker's most recent stderr lines to keep around for error
# messages (see _drain_stderr). Everything older just gets dropped.
_STDERR_TAIL_LINES = 200

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Greedily packs sentences into chunks of at most `max_chars`, so a
    long narration line can be sent through an engine's fixed-generation-
    budget worker as several bounded calls instead of one that silently
    truncates. Splits on sentence boundaries (not mid-sentence) so each
    chunk is still natural to speak on its own; a single sentence longer
    than max_chars on its own becomes its own (oversized) chunk rather than
    being cut apart mid-word - rare in narration text, and still better
    than an engine truncating it further."""
    sentences = _SENTENCE_SPLIT_RE.split(text.replace("\n", " "))
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


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


class BaseWorkerSynthesizer:
    """Owns one long-lived isolated-venv worker subprocess and speaks to it
    over stdin/stdout for every synthesize() call, so the model loads onto
    the GPU once per production run instead of once per panel. Subclasses
    fill in: `tool_name` (selects `.tools/venv-<tool_name>`), `display_name`
    (for console messages), `_spawn_worker()` (the process command line),
    and `_build_request()` (the per-call JSON payload)."""

    tool_name: str = ""
    display_name: str = ""

    # Subclasses opt in when their engine has a fixed per-call generation
    # budget that silently truncates the audio - no error, it just stops
    # partway through - once the input text needs more than that budget's
    # worth of output (a fixed max_new_tokens budget, say).
    # None (the default) means synthesize() always makes exactly one call,
    # unchanged from before this existed.
    chunk_max_chars: int | None = None

    def __init__(self, audio_config: AudioConfig, model_manager: ModelManager):
        self.audio_config = audio_config
        self.model_manager = model_manager
        self._proc: subprocess.Popen | None = None
        self._stderr_tail: collections.deque = collections.deque(maxlen=_STDERR_TAIL_LINES)
        self._stderr_thread: threading.Thread | None = None
        atexit.register(self.shutdown)

    # --- subclass hooks -----------------------------------------------
    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        raise NotImplementedError

    def _build_request(self, text: str, voice: str, output_wav: Path) -> dict[str, Any]:
        """One synthesize request. `voice` is whatever identifies the
        narrator to this engine - a name for an engine with fixed voices, a
        reference-clip path for one that clones."""
        raise NotImplementedError

    def _synth_timeout_seconds(self) -> float:
        raise NotImplementedError

    def _post_synthesize(self, output_wav: Path, request: dict[str, Any]) -> None:
        """Optional per-engine post-processing after a successful synthesis
        (e.g. an ffmpeg-atempo speed fallback). No-op by default."""

    # --- shared worker-process machinery -------------------------------
    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        """Runs for the lifetime of one worker process, on its own daemon
        thread, continuously reading its stderr so the pipe can never fill
        up and block the worker's next write to it - see kokoro_worker.py's
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

    def synthesize(self, text: str, voice: str, output_wav: Path) -> None:
        """Synthesizes speech via this engine's worker process. Text longer
        than `chunk_max_chars` (when the engine sets one) is split on
        sentence boundaries into several bounded calls first and the
        resulting clips re-joined into `output_wav` - see chunk_max_chars'
        docstring above for why. The rest of the pipeline never sees the
        difference: still exactly one WAV at `output_wav` either way."""
        if self.chunk_max_chars and len(text) > self.chunk_max_chars:
            chunks = _split_text_into_chunks(text, self.chunk_max_chars)
            if len(chunks) > 1:
                self._synthesize_chunks(chunks, voice, output_wav)
                return
        self._synthesize_once(text, voice, output_wav)

    def _synthesize_once(self, text: str, voice: str, output_wav: Path) -> None:
        """One bounded worker call, start to finish - what synthesize() used
        to do inline before chunking existed. Also what each individual
        chunk goes through in the chunked path below."""
        proc = self._ensure_worker()
        request = self._build_request(text, voice, output_wav)

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

    def _synthesize_chunks(self, chunks: list[str], voice: str, output_wav: Path) -> None:
        """Synthesizes each chunk to its own temp WAV via the normal
        single-call path (so per-chunk post-processing like the speed
        ffmpeg-atempo fallback still applies), concatenates them in order,
        and atomically replaces `output_wav` with the joined result. Temp
        parts are always cleaned up, success or failure."""
        from pydub import AudioSegment  # already a hard dependency (see audio/tts.py)

        part_paths: list[Path] = []
        try:
            for i, chunk in enumerate(chunks):
                # ".wav" suffix kept last (not ".wav.tmp") - some workers
                # pick their output format from
                # the file extension and error on anything else.
                part_path = output_wav.with_name(f"{output_wav.stem}.chunk{i:03d}.tmp.wav")
                self._synthesize_once(chunk, voice, part_path)
                part_paths.append(part_path)

            combined = AudioSegment.empty()
            for part_path in part_paths:
                combined += AudioSegment.from_file(part_path)

            tmp_output = output_wav.with_name(output_wav.name + ".tmp")
            combined.export(tmp_output, format="wav")
            tmp_output.replace(output_wav)
        finally:
            for part_path in part_paths:
                part_path.unlink(missing_ok=True)

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


