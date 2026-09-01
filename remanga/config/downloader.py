"""MangaDex downloader settings - see remanga/downloader/."""

from __future__ import annotations

from pydantic import BaseModel


class DownloaderConfig(BaseModel):
    language: str = "en"
    image_quality: str = "data"  # 'data' (high quality) or 'data-saver'
    max_retries: int = 3
    retry_delay_seconds: int = 2
    request_delay_seconds: float = 0.35
    # pages.zip is a standalone convenience bundle of the raw downloaded page
    # images - nothing downstream in the pipeline reads it (cropping reads
    # straight from pages/), it's only useful for manually handing a chapter's
    # pages to an LLM, which isn't the marking workflow anymore (see
    # remanga/webui/). Off by default so a normal run doesn't spend time/disk
    # zipping something nothing needs; flip to true if you still want it.
    # Named for exactly what it does (zips the downloaded pages) so it's
    # never confused with cropper.package below, which zips something
    # completely different (the cropped panels/sheets).
    zip_pages_enabled: bool = False
