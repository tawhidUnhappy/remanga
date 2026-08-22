#!/usr/bin/env python3
"""Standalone MAGI v3 panel-detection worker - runs inside the isolated
`.venv-magi` environment as a one-shot batch subprocess, spoken to by
remanga/webui/magi_assist.py (in the main env) over a line-delimited JSON
protocol. Zero dependency on the `remanga` package itself.

Usage: magi_worker.py --repo_id ... --model_dir ... --score_threshold 0.5
Page image paths are read one per line from stdin (an empty stdin, i.e. EOF
immediately, is a valid "just verify the model loads" invocation). Output,
one JSON line per event, on stdout:
  {"event": "ready"}                                     once the model is loaded
  {"event": "error", "error": "..."}                     load failure - exits 1
  {"filename": "...", "boxes": [[x1,y1,x2,y2], ...]}      once per page processed
  {"event": "page_error", "filename": "...", "error": "..."}  one page failed - continues
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

real_stdout = sys.stdout


def send(obj: dict) -> None:
    real_stdout.write(json.dumps(obj) + "\n")
    real_stdout.flush()


def read_image_as_np(path: Path):
    import numpy as np
    from PIL import Image
    # Matches the model card's own preprocessing recipe (greyscale round-trip
    # normalizes scanlator color-tone/JPEG artifacts before detection).
    with Image.open(path) as img:
        return np.array(img.convert("L").convert("RGB"))


def extract_panel_boxes(page_result: dict, score_threshold: float):
    boxes = page_result.get("panels")
    if boxes is None:
        boxes = page_result.get("panel_bboxes") or page_result.get("panels_bboxes")
    if boxes is None:
        return []
    scores = page_result.get("panel_scores") or page_result.get("scores")
    if scores is not None and len(scores) == len(boxes):
        boxes = [b for b, s in zip(boxes, scores) if float(s) >= score_threshold]
    return [[float(v) for v in box] for box in boxes]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo_id", required=True)
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--score_threshold", type=float, default=0.5)
    args = parser.parse_args()

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        if not torch.cuda.is_available():
            send({"event": "error", "error": "No CUDA GPU available in .venv-magi's environment."})
            return 1

        model = AutoModelForCausalLM.from_pretrained(
            args.repo_id, torch_dtype=torch.float16, trust_remote_code=True, cache_dir=args.model_dir,
        ).cuda().eval()
        processor = AutoProcessor.from_pretrained(args.repo_id, trust_remote_code=True, cache_dir=args.model_dir)
    except Exception as e:
        send({"event": "error", "error": str(e)})
        return 1

    send({"event": "ready"})

    for line in sys.stdin:
        path_str = line.strip()
        if not path_str:
            continue
        path = Path(path_str)
        try:
            image = read_image_as_np(path)
            with torch.no_grad():
                raw = model.predict_detections_and_associations([image], processor)
            page_result = raw[0] if isinstance(raw, list) else raw
            boxes = extract_panel_boxes(page_result, args.score_threshold)
            send({"filename": path.name, "boxes": boxes})
        except Exception as e:
            send({"event": "page_error", "filename": path.name, "error": str(e)})

    return 0


if __name__ == "__main__":
    sys.exit(main())
