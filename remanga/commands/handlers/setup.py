"""Handlers for the Setup commands: settings, shared asset paths, and model
weights."""

from __future__ import annotations

from typing import Any, Dict

from remanga.config import RemangaConfig
from remanga.settings import run_paths_manager, run_setup_wizard


def setup_config(params: Dict[str, Any], config: RemangaConfig) -> None:
    run_setup_wizard(config)


def paths(params: Dict[str, Any], config: RemangaConfig) -> None:
    run_paths_manager(config)


def setup_models(params: Dict[str, Any], config: RemangaConfig) -> None:
    """Downloads/verifies every model the current configuration will
    actually use.

    Only the currently-configured TTS engine's weights are fetched -
    switching tts.engine later downloads the other engine's weights the
    first time it's used, same as every engine's own lazy ensure_model()
    already does. Each ensure_model() call below reuses the owning
    component's own ModelManager rather than building a second one here, so
    repo ids and expected files live in exactly one place per model."""
    from remanga.audio.synth import create_synthesizer
    from remanga.ocr import OCREngine
    from remanga.webui.magi_assist import ensure_weights_downloaded

    create_synthesizer(config.tts, config.audio).model_manager.ensure_model()
    ensure_weights_downloaded(config.marker)
    # DeepSeek-OCR-2 powers the Narration Writer's "OCR this panel" button.
    OCREngine(config.ocr).model_manager.ensure_model()
