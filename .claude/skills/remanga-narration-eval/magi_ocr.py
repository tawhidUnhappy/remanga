"""MAGI v3's reading of a chapter's pages - every text with its box and its OCR, which texts are story (not
sound effects), the text-tail and text-character links, and the characters grouped on each page - for
gold.py to draft a gold transcript from.

    .tools/venv-magi/bin/python -I .claude/skills/remanga-narration-eval/magi_ocr.py PAGES_DIR OUT.json [first-last]

Runs in MAGI's own environment with the weights remanga already has (checkpoints/magiv3): about 1.9 GB of
GPU memory and 2-3 s a page on a 12 GB card - leave it until no render holds the GPU."""
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

pages_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
pages = sorted(p for p in pages_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
if len(sys.argv) > 3:
    a, b = map(int, sys.argv[3].split("-"))
    pages = pages[a - 1:b]
repo, cache = "ragavsachdeva/magiv3", str(Path(__file__).resolve().parents[3] / "checkpoints" / "magiv3")
t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(repo, torch_dtype=torch.float16, trust_remote_code=True,
                                             cache_dir=cache).cuda().eval()
processor = AutoProcessor.from_pretrained(repo, trust_remote_code=True, cache_dir=cache)
print(f"loaded in {time.time() - t0:.0f}s, VRAM {torch.cuda.memory_allocated() / 2**30:.1f} GB", flush=True)
result = {}
for path in pages:
    t = time.time()
    image = np.array(Image.open(path).convert("RGB"))
    with torch.no_grad():
        det = model.predict_detections_and_associations([image], processor)[0]
        ocr = model.predict_ocr([image], processor)[0]
    def to_list(x):
        return x.tolist() if hasattr(x, "tolist") else x
    result[path.name] = {
        "size": [image.shape[1], image.shape[0]],
        "texts": to_list(det["texts"]), "characters": to_list(det["characters"]), "tails": to_list(det["tails"]),
        "panels": to_list(det["panels"]),
        "essential": to_list(det["is_essential_text"]),
        "text_character": to_list(det["text_character_associations"]),
        "text_tail": to_list(det["text_tail_associations"]),
        "character_clusters": to_list(det["character_cluster_labels"]),
        "ocr": [{"text": s.strip(), "box": to_list(b)} for s, b in zip(ocr["ocr_texts"], ocr["bboxes"], strict=False)],
    }
    print(f"{path.name}: {len(result[path.name]['ocr'])} ocr, {len(det['texts'])} texts in {time.time() - t:.1f}s",
          flush=True)
out.write_text(json.dumps(result, indent=1, ensure_ascii=False))
print("peak VRAM", round(torch.cuda.max_memory_allocated() / 2**30, 1), "GB")
