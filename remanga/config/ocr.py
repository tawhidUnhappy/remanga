"""DeepSeek-OCR-2 settings - see remanga/ocr/engine.py, remanga/models/weights.py
(ModelManager) and remanga/models/scripts/download_deepseek_ocr.py.

Powers the Narration Writer's "OCR this panel" button. Apache-2.0, ~3B
parameters, and it ships its own modeling code (trust_remote_code=True).
Runs in its own isolated `.tools/venv-deepseek-ocr`, which it genuinely
needs: it pins `transformers==4.46.3`, while MAGI v3 wants <4.52 and nothing
else in the repo would tolerate being held that far back."""

from __future__ import annotations

from typing import Any

from pydantic import model_validator

from remanga.config.base import ConfigModel

# OCR models this repo has driven before. A config.json still naming one of
# these is reset to the current model's defaults rather than obeyed.
RETIRED_REPO_IDS = {"lightonai/lightonocr-2-1b"}


class OCRConfig(ConfigModel):
    hf_repo_id: str = "deepseek-ai/DeepSeek-OCR-2"
    model_dir: str = "checkpoints/deepseek_ocr_2"
    # The model's own prompt presets. "Free OCR." reads the text and nothing
    # else, which is what a manga panel wants; the alternative documented mode
    # ("<image>\n<|grounding|>Convert the document to markdown.") adds layout
    # markup that is meaningless for a speech bubble and only has to be
    # stripped again afterwards (see ocr/cleanup.py).
    prompt: str = "<image>\nFree OCR."
    # Resolution the page is processed at, from the model card's own example.
    # base_size is the canvas, image_size the tile; crop_mode tiles a large
    # page instead of downscaling it, which is what keeps small lettering
    # legible.
    base_size: int = 1024
    image_size: int = 768
    crop_mode: bool = True

    @model_validator(mode="before")
    @classmethod
    def _migrate_retired_models(cls, data: Any) -> Any:
        """Drops settings left behind by an OCR model that is no longer wired
        up.

        Field names overlap between models - `hf_repo_id`, `model_dir` and
        `prompt` all exist either way - so an untouched config.json does NOT
        fail validation when the model changes. It quietly keeps pointing at
        the old repo, and the first OCR click downloads several GB of the
        wrong model into a directory named after it. Naming the retired ids
        here is what turns that silent wrong answer into a no-op."""
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        if str(migrated.get("hf_repo_id", "")).strip().lower() in RETIRED_REPO_IDS:
            for field_name in ("hf_repo_id", "model_dir", "prompt"):
                migrated.pop(field_name, None)
        # Sampling knob belonging to a retired model; harmless but meaningless.
        migrated.pop("max_new_tokens", None)
        return migrated
