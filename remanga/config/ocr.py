"""DeepSeek-OCR settings - see remanga/models/weights.py (ModelManager) and
remanga/models/scripts/download_deepseek_ocr.py.

Download-only for now: no pipeline step actually consumes this model yet
(remanga has no OCR-based feature today) - this just wires DeepSeek-OCR-2's
weights into `remanga setup-models` the same way IndexTTS-2.5, Audio8 TTS,
and MAGI v3 already get fetched/verified there (isolated venv, ModelScope-
first with a Hugging Face Hub fallback, skip-if-present), so the weights are
sitting in checkpoints/ ready for whenever an actual OCR step gets built on
top of it."""

from __future__ import annotations

from pydantic import BaseModel


class OCRConfig(BaseModel):
    hf_repo_id: str = "deepseek-ai/DeepSeek-OCR-2"
    model_dir: str = "checkpoints/deepseek_ocr_2"
