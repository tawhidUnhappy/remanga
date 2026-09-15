"""What a pipeline step is. Its own module, with nothing heavy in it, so an
extension can declare a step without importing the pipeline that is loading
it (see remanga.extensions.spec)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remanga.config import RemangaConfig


@dataclass
class Step:
    """One pipeline step. `run` takes (project, chapter, config) - the same
    signature for every step, regardless of what extra state a given step
    happens to need (e.g. download resolves its own manga URL from
    project.json, same fallback MangaDexDownloader.download_chapter already
    has). `needs` is informational only - the prior step names this one
    normally expects to have already run - used for a soft warning in
    run_pipeline, not a real dependency-graph resolver."""
    name: str
    description: str
    run: Callable[[str, str, RemangaConfig], None]
    needs: list[str] = field(default_factory=list)
