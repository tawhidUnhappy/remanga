"""OCREngine: one long-lived `.tools/venv-deepseek-ocr` worker subprocess
(remanga/ocr/scripts/deepseek_ocr_worker.py), spoken to over stdin/stdout so
DeepSeek-OCR-2 loads onto the GPU once per Narration Writer session instead
of once per "OCR this panel" click.

The worker lifecycle - spawn, ready handshake, auto-heal a missing
dependency, bounded-timeout requests, stderr draining so a wedged worker
can't deadlock, clean shutdown - is remanga/workers/, shared with the TTS
engines. Only what OCR does differently is here: the command line, the
recognize request, and cleaning up the text that comes back."""

from __future__ import annotations

import subprocess
from pathlib import Path

from remanga.config import OCRConfig
from remanga.console import console
from remanga.models.weights import ModelManager
from remanga.ocr.cleanup import clean_ocr_text
from remanga.workers import ToolWorker, spawn_script_worker

# Generous but bounded, same reasoning as TTSConfig's own
# synth_timeout_seconds: a wedged worker should fail clearly, not hang the
# Narration Writer UI's request forever. A 1B model reading one panel is
# well inside this on a GPU; CPU is far slower, which is what the ceiling
# is sized for.
_RECOGNIZE_TIMEOUT_SECONDS = 120.0

TOOL_NAME = "deepseek-ocr"
DISPLAY_NAME = "DeepSeek-OCR-2"


class OCREngine(ToolWorker):
    """One instance per Narration Writer session (see writer_state.py) -
    lazily spawns its worker (and, before that, downloads the model weights
    if they aren't already present - same lazy-fetch-on-first-use pattern
    every TTS engine already follows) on the *first* recognize() call, so
    opening the Narration Writer never pays GPU/model-load cost unless the
    user actually clicks "OCR this panel"."""

    tool_name = TOOL_NAME
    display_name = DISPLAY_NAME
    # This engine runs on whatever it finds, and which one it got is worth
    # knowing before the first panel takes a minute.
    starting_note = " (prefers GPU, falls back to CPU)"

    def __init__(self, ocr_config: OCRConfig):
        self.ocr_config = ocr_config
        self.model_manager = ModelManager(
            ocr_config.model_dir, ocr_config.hf_repo_id,
            tool_name=TOOL_NAME, download_script="download_deepseek_ocr.py",
            expected_files=("config.json", "model-00001-of-000001.safetensors"), display_name=DISPLAY_NAME,
        )
        self.device: str | None = None
        self._init_worker_state()

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        return spawn_script_worker(TOOL_NAME, "ocr", "deepseek_ocr_worker.py", str(model_dir.resolve()))

    def _on_ready(self, event: dict) -> None:
        self.device = event.get("device")
        console.print(
            f"[bold green]✓ {DISPLAY_NAME} worker ready[/] "
            f"[dim]({'GPU' if self.device == 'cuda' else 'CPU - no GPU available'})[/]"
        )

    def recognize(self, image_path: Path, prompt: str | None = None) -> str:
        """Runs OCR on one panel image, returning the recognized text (empty
        string if the model found none). Raises RuntimeError on a worker
        failure/timeout - the caller (writer_routes.py) turns that into an
        HTTP error the frontend surfaces, not a crash."""
        request = {
            "cmd": "recognize",
            "image_path": str(Path(image_path).resolve()),
            "base_size": self.ocr_config.base_size,
            "image_size": self.ocr_config.image_size,
            "crop_mode": self.ocr_config.crop_mode,
        }
        # An explicit argument wins over the configured default, and an empty
        # prompt is sent as nothing at all rather than as an empty text turn -
        # see the worker for why those are not the same to the chat template.
        chosen = prompt if prompt is not None else self.ocr_config.prompt
        if chosen:
            request["prompt"] = chosen

        response = self._request(request, _RECOGNIZE_TIMEOUT_SECONDS, action="recognition")
        # Cleaned here rather than in the worker: the worker is meant to be a
        # thin, dependency-free shell around the model, and this is a
        # judgement about output quality that belongs where it can be read and
        # changed without touching the isolated environment. See ocr/cleanup.py
        # for why the model needs it at all.
        return clean_ocr_text(response.get("text", ""))
