"""Reading a batch's word timings back off its audio.

The driver side of `.tools/venv-faster-whisper`/whisper_words_worker.py -
one worker for the whole chapter, the same shape as the TTS engines'
(remanga/workers/). It is asked for one batch at a time and writes each
batch's words beside it in the subtitles folder."""

from __future__ import annotations

import contextlib
import subprocess
import wave
from pathlib import Path
from typing import Any

from remanga.config import SubtitlesConfig
from remanga.models import ModelManager
from remanga.workers import ToolWorker, spawn_script_worker

TOOL_NAME = "faster-whisper"
DISPLAY_NAME = "faster-whisper"

# What proves the download finished: the converted weights, the tokenizer and
# the converter's config are all needed before the model will load at all.
EXPECTED_FILES = ("model.bin", "config.json", "tokenizer.json")

# How long one batch may take. Measured at 0.10x real time on this machine
# (14s for a 142s take), so the audio's own length times four is generous
# even on a cold cache, and the floor covers a short batch where loading
# dominates. Not the TTS timeout: transcription is an order of magnitude
# faster than synthesis and sharing one number would make it meaningless.
TIMEOUT_FLOOR_SECONDS = 180.0
TIMEOUT_PER_AUDIO_SECOND = 4.0


def audio_seconds(path: Path) -> float:
    """How long a WAV is, from its header - nothing here needs the samples."""
    with contextlib.closing(wave.open(str(path), "rb")) as handle:
        return handle.getnframes() / float(handle.getframerate())


class Transcriber(ToolWorker):
    """faster-whisper, asked only ever for WHEN each word was said."""

    tool_name = TOOL_NAME
    display_name = DISPLAY_NAME

    def __init__(self, config: SubtitlesConfig):
        self.config = config
        self.model_manager = ModelManager(
            config.model_dir, config.hf_repo_id, tool_name=TOOL_NAME,
            download_script="download_whisper.py", expected_files=EXPECTED_FILES,
            display_name=DISPLAY_NAME,
        )
        self._init_worker_state()

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        return spawn_script_worker(
            TOOL_NAME, "subtitles", "whisper_words_worker.py",
            "--model", str(model_dir.resolve()),
            "--language", self.config.language,
            "--compute_type", self.config.compute_type,
        )

    def words_for(self, audio_wav: Path, out_json: Path) -> dict[str, Any]:
        """Writes `audio_wav`'s word timings to `out_json` and returns what
        the worker said about them."""
        timeout = max(TIMEOUT_FLOOR_SECONDS, audio_seconds(audio_wav) * TIMEOUT_PER_AUDIO_SECOND)
        return self._request(
            {"cmd": "transcribe", "audio_path": str(audio_wav.resolve()),
             "output_path": str(out_json.resolve())},
            timeout, action="transcription",
            on_timeout=f" on {audio_wav.name}",
            advice=" Safe to re-run; batches already read are reused.",
        )
