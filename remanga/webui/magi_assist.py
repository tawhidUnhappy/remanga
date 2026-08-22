"""MAGI v3 panel-detection assist for the panel-marking web UI.

MAGI (https://github.com/ragavsachdeva/magi, https://huggingface.co/ragavsachdeva/magiv3)
is a manga-understanding vision-language model from Oxford (Sachdeva & Zisserman)
that localizes panels, characters, text blocks, and speech-bubble tails on a raw
page image. This module only uses its panel detection: it pre-fills every page's
panel boxes so a person only has to adjust them in the web UI, not draw from
scratch (`remanga/webui/server.py` calls `detect_panels_for_pages`).

License note: the magiv3 model card permits "personal, research, non-commercial,
and not-for-profit" use only - fine for running your own chapters through this
tool, not something to bundle into a redistributed commercial product as-is.

Requires a CUDA GPU. Lazily loaded on first use (and only if `marker.magi_enabled`
is true in config) so nothing about this pipeline stage costs anything when it's
turned off.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image
from rich.console import Console

from remanga.config import MarkerConfig

console = Console()

# One process-wide cache: the model is a multi-GB vision-language transformer,
# never reload it just because a second chapter/page batch comes through.
_model = None
_processor = None
_loaded_repo_id: Optional[str] = None


def is_gpu_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def ensure_weights_downloaded(config: MarkerConfig) -> Optional[Path]:
    """Pre-fetches the MAGI v3 weights via the HF Hub, without loading them onto
    a GPU - called from `remanga setup-models` / bootstrap.sh, the same moment
    IndexTTS-2.5's weights are fetched, so the panel-marking assist is ready the
    first time someone actually opens the web UI. No-ops (with a note) if MAGI is
    disabled in config, or if there's no GPU to ever run it on."""
    if not config.magi_enabled:
        console.print("[dim]MAGI v3 assist is disabled (marker.magi_enabled=false) - skipping weight download.[/]")
        return None

    if not is_gpu_available():
        console.print(
            "[yellow]No CUDA GPU detected - skipping MAGI v3 weight download. "
            "The panel-marking web UI still works without it (mark panels manually).[/]"
        )
        return None

    from huggingface_hub import snapshot_download

    model_dir = Path(config.magi_model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    # `cache_dir`, not `local_dir` - this must match the `cache_dir=` passed to
    # AutoModelForCausalLM.from_pretrained() in _load() above, or the two use
    # different on-disk layouts and _load() ends up re-downloading everything.
    with console.status(f"[bold cyan]Fetching MAGI v3 weights ({config.magi_repo_id})...[/]", spinner="dots"):
        snapshot_download(repo_id=config.magi_repo_id, cache_dir=str(model_dir))

    console.print(f"[bold green]✓ MAGI v3 weights ready:[/] {model_dir}")
    return model_dir


def _load(config: MarkerConfig):
    global _model, _processor, _loaded_repo_id

    if _model is not None and _loaded_repo_id == config.magi_repo_id:
        return _model, _processor

    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor

    if not torch.cuda.is_available():
        raise RuntimeError(
            "MAGI v3 assist requires a CUDA GPU, but none is available. "
            "Disable it via marker.magi_enabled=false in config.json, or mark panels manually."
        )

    with console.status(f"[bold cyan]Loading MAGI v3 ({config.magi_repo_id})...[/]", spinner="dots"):
        model = AutoModelForCausalLM.from_pretrained(
            config.magi_repo_id,
            torch_dtype=torch.float16,
            trust_remote_code=True,
            cache_dir=config.magi_model_dir,
        ).cuda().eval()
        processor = AutoProcessor.from_pretrained(
            config.magi_repo_id,
            trust_remote_code=True,
            cache_dir=config.magi_model_dir,
        )

    _model, _processor, _loaded_repo_id = model, processor, config.magi_repo_id
    console.print("[bold green]✓ MAGI v3 loaded.[/]")
    return _model, _processor


def _read_image_as_np(path: Path) -> np.ndarray:
    # Matches the model card's own preprocessing recipe (greyscale round-trip
    # normalizes scanlator color-tone/JPEG artifacts before detection).
    with Image.open(path) as img:
        return np.array(img.convert("L").convert("RGB"))


def _extract_panel_boxes(page_result: Dict[str, Any], score_threshold: float) -> List[List[float]]:
    """Best-effort extraction of panel boxes from one page's raw MAGI result.
    The model already applies its own detection threshold and overlap
    suppression internally per its published postprocessing, so this mostly
    just locates the right key across the couple of naming variants seen in
    MAGI's own examples/source, plus an optional extra score filter."""
    boxes = page_result.get("panels")
    if boxes is None:
        boxes = page_result.get("panel_bboxes") or page_result.get("panels_bboxes")
    if boxes is None:
        return []

    scores = page_result.get("panel_scores") or page_result.get("scores")
    if scores is not None and len(scores) == len(boxes):
        boxes = [b for b, s in zip(boxes, scores) if float(s) >= score_threshold]

    return [[float(v) for v in box] for box in boxes]


def detect_panels_for_pages(
    page_paths: List[Path],
    config: MarkerConfig,
    on_page_done=None,
) -> Dict[str, List[List[float]]]:
    """Runs MAGI v3 panel detection over a batch of page images. Returns
    {page_filename: [[x1, y1, x2, y2], ...]} in pixel space. Calls
    `on_page_done(filename, boxes)` after each page if given, so a caller (the
    web server) can stream progress to the UI instead of blocking until the
    whole chapter finishes.
    """
    model, processor = _load(config)
    import torch

    results: Dict[str, List[List[float]]] = {}
    for path in page_paths:
        image = _read_image_as_np(path)
        with torch.no_grad():
            raw = model.predict_detections_and_associations([image], processor)
        page_result = raw[0] if isinstance(raw, list) else raw
        boxes = _extract_panel_boxes(page_result, config.magi_panel_score_threshold)
        results[path.name] = boxes
        if on_page_done:
            on_page_done(path.name, boxes)

    return results
