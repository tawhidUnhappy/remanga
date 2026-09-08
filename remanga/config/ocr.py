"""LightOn OCR settings - see remanga/ocr/engine.py, remanga/models/weights.py
(ModelManager) and remanga/models/scripts/download_lighton_ocr.py.

Powers the Narration Writer's "OCR this panel" button. Replaced
DeepSeek-OCR-2, whose interface this repo never actually got to verify - the
worker written against it guessed at `.infer()` from the v1 model card and
carried a fallback for reading whatever file it might have written instead.
LightOnOCR-2 needs none of that: it has first-class `transformers` support
(`LightOnOcrForConditionalGeneration` / `LightOnOcrProcessor`), so the worker
calls a documented API and gets the text back directly.

Apache-2.0, ~1B parameters, a Pixtral vision encoder with a Qwen3 decoder
distilled for document parsing. Runs in its own isolated
`.tools/venv-lighton-ocr`, which it genuinely needs: it requires
transformers>=5.0, and MAGI v3 pins transformers<4.52."""

from __future__ import annotations

from pydantic import BaseModel


class OCRConfig(BaseModel):
    hf_repo_id: str = "lightonai/LightOnOCR-2-1B"
    model_dir: str = "checkpoints/lighton_ocr_2_1b"
    # What the model is asked to do with a panel. LightOnOCR-2's own chat
    # template takes an image with no text turn at all for plain document
    # parsing, which is what an empty prompt here means - a manga panel is
    # closer to "read this page" than to a visual question. Set a string to
    # send an instruction alongside the image instead.
    prompt: str = ""
    # Ceiling on generated tokens for one panel. A speech bubble is short;
    # this is sized for a dense panel with several bubbles plus signage, not
    # for a full document page.
    max_new_tokens: int = 512
