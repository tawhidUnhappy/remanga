"""Downloader settings - see remanga/plugins/mangadex/ and remanga/plugins/browser/."""

from __future__ import annotations

from pydantic import Field

from remanga.config.base import ConfigModel


class DownloaderConfig(ConfigModel):
    language: str = "en"
    # A chapter nobody has put out in `language` is taken in the first of
    # these that has it ("*" = any language, the newest upload). The
    # narration is still written in English: the PDF tells the LLM which
    # language the lettering is in (remanga/languages.py).
    fallback_languages: list[str] = Field(default_factory=lambda: ["*"])
    image_quality: str = "data"  # 'data' (high quality) or 'data-saver'
    max_retries: int = 3
    retry_delay_seconds: int = 2
    request_delay_seconds: float = 0.35
    # Sites downloaded through your Firefox (remanga/plugins/browser/).
    # The Firefox profile it happens in, by the name Firefox shows ("" = Firefox's default).
    browser_profile: str = ""
    # Pause between two chapters, and between two screens while reading one
    # (each varied by +-30%) - a reader's pace, never faster.
    browser_chapter_pause_seconds: float = 10.0
    browser_scroll_seconds: float = 0.8
    # Pause between two pages of a site's chapter list (comix.to's firewall
    # asks for a check when it is turned quickly).
    browser_list_pause_seconds: float = 8.0
