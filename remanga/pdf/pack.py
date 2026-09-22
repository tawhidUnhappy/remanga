"""Packing panels into as many PDF parts as the size cap needs.

Splitting, not quality, is what keeps a file under the cap: parts are filled
in reading order and each one is built and measured exactly, since a PDF's
real size only shows once it is written. Only a single panel too big for a
part on its own gives up exactness (see encode.near_lossless_pages)."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from remanga.pdf.encode import PSNR_FLOORS, near_lossless_pages
from remanga.pdf.writer import ImagePage

# Bytes each image page adds to a PDF around its stream (image, content and
# page objects plus their xref lines) - an estimate for packing parts; every
# part is measured exactly once it is built.
_PAGE_OVERHEAD = 600

# Panels are encoded in parallel; the near-lossless fallback is the only
# per-panel work this module does itself.
_WORKERS = min(8, os.cpu_count() or 1)


@dataclass
class _Page:
    """One image and every encoding tried for it so far. `level` 0 is
    lossless; level n is the smallest encoding reaching PSNR_FLOORS[n - 1],
    or the lossless page when none is smaller."""

    stem: str
    path: Path
    lossless: ImagePage
    near: list[tuple[ImagePage, float]] | None = None
    level: int = 0

    def choice(self, level: int) -> tuple[ImagePage, float]:
        best = (self.lossless, float("inf"))
        if level == 0:
            return best
        for page, psnr in self.near or ():
            if psnr >= PSNR_FLOORS[level - 1] and len(page.data) < len(best[0].data):
                best = (page, psnr)
        return best

    def at(self, level: int) -> ImagePage:
        return self.choice(level)[0]

    @property
    def page(self) -> ImagePage:
        return self.at(self.level)

    @property
    def size(self) -> int:
        return len(self.page.data)


def _ensure_near(pages: Sequence[_Page]) -> None:
    todo = [page for page in pages if page.near is None]
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        for page, near in zip(todo, pool.map(lambda p: near_lossless_pages(p.path), todo), strict=True):
            page.near = near


@dataclass
class _Built:
    pdf: bytes

    @property
    def size(self) -> int:
        return len(self.pdf)


# Renders one part: (its pages, part number, part count) -> the file bytes.
Render = Callable[[Sequence[_Page], int, int], _Built]


def _fit_one_file(pages: Sequence[_Page], max_bytes: int, render: Render, index: int, total: int) -> _Built | None:
    """`pages` as one file of at most `max_bytes`, stepping pages down the
    quality floors only as far as that takes - every page to the next floor,
    biggest saving first, before any page to the one after. None when even
    the last floor doesn't fit."""
    built = render(pages, index, total)
    for level in range(1, len(PSNR_FLOORS) + 1):
        if built.size <= max_bytes:
            return built
        _ensure_near(pages)
        candidates = sorted((page for page in pages if page.level == level - 1),
                            key=lambda page: len(page.at(level - 1).data) - len(page.at(level).data), reverse=True)
        over = built.size - max_bytes
        for page in candidates:
            over -= len(page.at(page.level).data) - len(page.at(level).data)
            page.level = level
            if over <= 0:
                built = render(pages, index, total)
                if built.size <= max_bytes:
                    return built
                over = built.size - max_bytes
        built = render(pages, index, total)
    return built if built.size <= max_bytes else None


def _pack_parts(pages: list[_Page], max_bytes: int, render: Render) -> list[_Built] | None:
    """Splits `pages`, in order, into as many files of at most `max_bytes`
    as they need, every page lossless unless it can't fit in a file even on
    its own. None when such a page doesn't fit even at the last floor."""
    for page in pages:
        if render([page], 1, 1).size > max_bytes and _fit_one_file([page], max_bytes, render, 1, 1) is None:
            return None

    # Packed on an estimate, then measured: a part that comes out over the
    # cap (its info page or zip wrapper bigger than reserved) repacks with
    # that much more held back.
    reserve = render([], 1, 1).size
    for _ in range(10):
        parts: list[list[_Page]] = [[]]
        used = reserve
        for page in pages:
            need = page.size + _PAGE_OVERHEAD
            if parts[-1] and used + need > max_bytes:
                parts.append([])
                used = reserve
            parts[-1].append(page)
            used += need
        built = [render(part, idx, len(parts)) for idx, part in enumerate(parts, start=1)]
        worst = max(b.size for b in built)
        if worst <= max_bytes:
            return built
        reserve += worst - max_bytes
    return None


def _quality_note(pages: Sequence[_Page]) -> str:
    changed = [page.choice(page.level)[1] for page in pages if not page.page.lossless]
    if not changed:
        return f"all {len(pages)} panels lossless"
    return (f"{len(pages) - len(changed)} panels lossless, {len(changed)} near-lossless to fit "
            f"(lowest PSNR {min(changed):.1f} dB)")
