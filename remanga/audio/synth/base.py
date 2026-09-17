"""The synthesizer every TTS engine shares.

BaseWorkerSynthesizer turns synthesize() calls into requests to one
isolated-venv worker, splitting text an engine can't take in a single call.
The worker itself - spawn, ready handshake, auto-heal, bounded reads, stderr
draining, shutdown - is remanga/workers/. The engine subclass (chatterbox.py)
fills in only the command line and the per-request payload."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from remanga.config import AudioConfig
from remanga.models import ModelManager
from remanga.workers import ToolWorker

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# What synthesize() says about a page that timed out: that a re-run costs
# only that page.
_TIMEOUT_ADVICE = (" Safe to just re-run; already-synthesized pages are cached and this "
                   "one regenerates automatically.")


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


class BaseWorkerSynthesizer(ToolWorker):
    """Owns one long-lived isolated-venv worker subprocess and speaks to it
    over stdin/stdout for every synthesize() call, so the model loads onto
    the GPU once per run instead of once per page. Subclasses
    fill in: `tool_name` (selects `.tools/venv-<tool_name>`), `display_name`
    (for console messages), `_spawn_worker()` (the process command line),
    and `_build_request()` (the per-call JSON payload)."""

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
        self._init_worker_state()

    # --- subclass hooks -----------------------------------------------
    def _build_request(self, text: str, voice: str, output_wav: Path) -> dict[str, Any]:
        """One synthesize request. `voice` is whatever identifies the
        narrator to this engine - a name for an engine with fixed voices, a
        reference-clip path for one that clones."""
        raise NotImplementedError

    def _synth_timeout_seconds(self) -> float:
        raise NotImplementedError

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
        request = self._build_request(text, voice, output_wav)
        self._request(
            request, self._synth_timeout_seconds(), action="synthesis",
            on_timeout=f" on page text {text[:80]!r}", advice=_TIMEOUT_ADVICE,
        )

    def _synthesize_chunks(self, chunks: list[str], voice: str, output_wav: Path) -> None:
        """Synthesizes each chunk to its own temp WAV via the normal
        single-call path, concatenates them in order,
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
