"""Handlers for the Setup commands: settings, shared asset paths, and model
weights."""

from __future__ import annotations

from typing import Any

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.settings import run_paths_manager, run_setup_wizard


def setup_config(params: dict[str, Any], config: RemangaConfig) -> None:
    run_setup_wizard(config)


def paths(params: dict[str, Any], config: RemangaConfig) -> None:
    run_paths_manager(config)


def setup_models(params: dict[str, Any], config: RemangaConfig) -> None:
    """Downloads/verifies every model the current configuration will
    actually use.

    Each ensure_model() call below reuses the owning
    component's own ModelManager rather than building a second one here, so
    repo ids and expected files live in exactly one place per model."""
    from remanga.audio.synth import create_synthesizer
    from remanga.ocr import OCREngine
    from remanga.webui.magi_assist import ensure_weights_downloaded

    create_synthesizer(config.tts, config.audio).model_manager.ensure_model()
    ensure_weights_downloaded(config.marker)
    # DeepSeek-OCR-2 powers the Narration Writer's "OCR this panel" button.
    OCREngine(config.ocr).model_manager.ensure_model()


def hardware(params: dict[str, Any], config: RemangaConfig) -> None:
    """Prints what remanga detected about this machine, and what that means.

    The same detection bootstrap.sh used when it chose which wheels to
    install, so this is the way to check whether a machine actually got the
    GPU build it should have - and, when a render is unexpectedly slow, to
    tell "no GPU here" apart from "GPU present, encoder rejected it"."""
    from remanga.hardware import detect, ffmpeg_plan

    hw = detect()
    plan = ffmpeg_plan(hw)
    rows = [
        ("Platform", f"{hw.os}/{hw.arch}"),
        ("Accelerator", hw.accelerator),
        ("Device", hw.device_name or "-"),
        ("Driver", hw.driver_version or "-"),
        ("PyTorch wheels", hw.torch_backend if hw.torch_backend != "default" else "pypi/default"),
        ("Wheel index", hw.torch_index_url or "https://pypi.org/simple"),
        ("FFmpeg", f"{plan['kind']}{'/' + plan['asset'] if plan['asset'] else ''}"),
        ("Video encoder", config.system.resolve_gpu_codec()),
        ("  (configured)", config.system.gpu_codec),
        ("CPU fallback", config.system.fallback_codec),
    ]
    width = max(len(label) for label, _ in rows)
    console.print("[bold]Detected hardware[/]")
    for label, value in rows:
        console.print(f"  [dim]{label.ljust(width)}[/]  {_esc(str(value))}")
    for note in hw.notes:
        console.print(f"\n[yellow]{_esc(note)}[/]")
    console.print(
        "\n[dim]Override the wheel choice by setting REMANGA_TORCH_BACKEND "
        "(cpu, cu126, cu128, rocm6.4, ...) and re-running ./bootstrap.sh.[/]"
    )
