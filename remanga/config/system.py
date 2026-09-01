"""System-wide settings: GPU/codec preference and logging."""

from __future__ import annotations

from pydantic import BaseModel


class SystemConfig(BaseModel):
    prefer_gpu: bool = True
    gpu_codec: str = "h264_nvenc"
    fallback_codec: str = "libx264"
    threads: int = 4
    log_level: str = "INFO"
