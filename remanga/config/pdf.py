"""The pages PDF - see remanga/pdf/builder.py."""

from __future__ import annotations

from pydantic import Field

from remanga.config.base import ConfigModel


class PdfConfig(ConfigModel):
    # No PDF file is ever larger than this, in MB: a chapter that doesn't fit
    # in one is split into pages_1.pdf, pages_2.pdf, ...
    max_mb: float = Field(50.0, gt=0)
