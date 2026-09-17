"""MangaDex downloader settings - see remanga/downloader/."""

from __future__ import annotations

from remanga.config.base import ConfigModel


class DownloaderConfig(ConfigModel):
    language: str = "en"
    image_quality: str = "data"  # 'data' (high quality) or 'data-saver'
    max_retries: int = 3
    retry_delay_seconds: int = 2
    request_delay_seconds: float = 0.35
