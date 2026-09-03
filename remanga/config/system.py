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
    # remanga/hf_token.py for the full contract. Defaults to global/hf_token.json
    # - remanga/paths/global_assets.py:ensure_hf_token_file() creates it with
    # a blank {"token": ""} the first time any model download runs, so
    # there's always a real place to drop a token in without editing
    # config.json first. A blank "token" value there is silently treated as
    # "not configured" (unauthenticated, today's behavior) - only a
    # malformed file or one missing the "token" key entirely warns.
    hf_token_path: str = "global/hf_token.json"
