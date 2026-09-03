"""System-wide settings: GPU/codec preference and logging."""

from __future__ import annotations

from pydantic import BaseModel


class SystemConfig(BaseModel):
    prefer_gpu: bool = True
    gpu_codec: str = "h264_nvenc"
    fallback_codec: str = "libx264"
    threads: int = 4
    log_level: str = "INFO"

    # Path to a small JSON file holding {"token": "hf_..."} - used by every
    # model download (IndexTTS-2.5, Audio8 TTS, MAGI v3, DeepSeek-OCR-2) to
    # raise Hugging Face Hub's unauthenticated rate limit/speed, if set. See
    # remanga/hf_token.py for the full contract. Empty by default - every
    # download just stays unauthenticated exactly like today until this is
    # actually pointed at a real file.
    hf_token_path: str = ""
