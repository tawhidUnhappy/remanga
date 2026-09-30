"""A long-strip chapter's downloaded images as strips: consecutive images of
one width joined top to bottom (a "run"), and where each sits in the whole
chapter read top to bottom.

Every row number in remanga/longstrip is a row of that whole chapter - the
downloaded images stacked in order, each at its own natural size. A cover or
a credits page of another width is a run of its own."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps


@dataclass(frozen=True)
class Run:
    paths: tuple[Path, ...]
    top: int      # first row in the whole chapter
    width: int
    height: int

    @property
    def bottom(self) -> int:
        return self.top + self.height


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).size


def runs_of(sources: list[Path]) -> list[Run]:
    """The runs of these images, in order. Reads image headers only."""
    groups: list[list[tuple[Path, int, int]]] = []
    for path in sources:
        width, height = _size(path)
        if groups and groups[-1][0][1] == width:
            groups[-1].append((path, width, height))
        else:
            groups.append([(path, width, height)])
    runs, top = [], 0
    for group in groups:
        height = sum(h for _, _, h in group)
        runs.append(Run(tuple(p for p, _, _ in group), top, group[0][1], height))
        top += height
    return runs


def stitch(run: Run) -> Image.Image:
    """The run as one RGB image."""
    strip = Image.new("RGB", (run.width, run.height))
    y = 0
    for path in run.paths:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            strip.paste(img, (0, y))
            y += img.height
    return strip

