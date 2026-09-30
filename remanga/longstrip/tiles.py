"""The strip as the Strip Marker's browser tab loads it: small JPEG tiles,
never whole downloaded images.

A downloaded image is up to 720x9900 and a chapter ~90,000 rows; putting them
all in a page (and a canvas the same size over each) is what made the first
Strip Marker lag. The tab shows only the tiles near what is on screen, each a
slice of one run (runs.py) about twice as tall as it is wide, scaled down to
at most TILE_MAX_WIDTH. Runs are stitched once and kept for the session."""

from __future__ import annotations

import io
import math
import threading

from PIL import Image

from remanga.longstrip.detect import Detection, detect
from remanga.longstrip.runs import Run, stitch

TILE_ASPECT = 2            # tile rows = run width x this
TILE_MAX_WIDTH = 900
TILE_QUALITY = 88


class StripView:
    """One chapter's runs, stitched on first use; tiles and detection from them."""

    def __init__(self, runs: list[Run]):
        self.runs = runs
        self._images: dict[int, Image.Image] = {}
        self._lock = threading.Lock()

    def image(self, index: int) -> Image.Image:
        with self._lock:
            if index not in self._images:
                self._images[index] = stitch(self.runs[index])
            return self._images[index]

    def tile_rows(self, index: int) -> int:
        return self.runs[index].width * TILE_ASPECT

    def layout(self) -> list[dict]:
        """Every run's place and tiling, for the tab to lay the strip out."""
        return [{"top": run.top, "height": run.height, "width": run.width, "tile_rows": self.tile_rows(i),
                 "tiles": math.ceil(run.height / self.tile_rows(i))} for i, run in enumerate(self.runs)]

    def tile(self, index: int, number: int) -> bytes:
        run, rows = self.runs[index], self.tile_rows(index)
        top = number * rows
        if not 0 <= top < run.height:
            raise IndexError(f"run {index} has no tile {number}")
        piece = self.image(index).crop((0, top, run.width, min(run.height, top + rows)))
        if piece.width > TILE_MAX_WIDTH:
            piece = piece.resize((TILE_MAX_WIDTH, round(piece.height * TILE_MAX_WIDTH / piece.width)),
                                 Image.Resampling.LANCZOS)
        out = io.BytesIO()
        piece.save(out, "JPEG", quality=TILE_QUALITY)
        return out.getvalue()

    def detect(self) -> list[Detection]:
        """Each run's detection, in its own rows."""
        return [detect(self.image(i)) for i in range(len(self.runs))]
