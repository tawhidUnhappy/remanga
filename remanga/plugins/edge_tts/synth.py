"""Edge voices - talks to `.tools/venv-edge-tts`/edge_tts_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.plugins import get
from remanga.workers import spawn_script_worker

SPEC = get("tts", "edge")


class NoWeights:
    """The voices are Microsoft's online service: nothing to download. The
    worker base asks for a model folder all the same, so this hands it one
    that is never read."""

    def ensure_model(self) -> Path:
        return Path()


class EdgeSynthesizer(BaseWorkerSynthesizer):
    """Edge voices - talks to `.tools/venv-edge-tts`/edge_tts_worker.py."""

    tool_name = SPEC.tool_name
    display_name = SPEC.display_name

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.edge
        super().__init__(audio_config, NoWeights())

    # No take limit, as for Kokoro: edge-tts splits whatever it is given into
    # pieces the service accepts and reads each in the same fixed voice - a
    # neural voice that does not sample, so it cannot wander over a chapter
    # the way Ming's built-in voices do. A whole chapter is one take.
    max_take_seconds = float("inf")

    # Measured in en-US-GuyNeural at the service's own pace: HimeSama chapter
    # 1, 14,156 chars -> 842.9s (in 90s).
    chars_per_second = 16.8

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        return spawn_script_worker("edge-tts", "plugins/edge_tts", "edge_tts_worker.py")

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, output_wav: Path, voice: str | None = None) -> dict[str, Any]:
        return {
            "cmd": "synthesize",
            "voice": voice or self.engine_config.spec.name,
            "text": text,
            "output_path": str(output_wav.resolve()),
        }
