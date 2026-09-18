"""A chapter's panels as PDF files for the LLM, never over the size cap.

Every panel starts lossless: a JPEG panel is embedded as its own bytes (the
downloaded file exactly, and far smaller than any re-encoding of its pixels),
any other panel in the smaller of two verified lossless encodings (PNG row
filters or TIFF Predictor 2), one channel instead of three when it is pure
grayscale. Panels are packed in reading order into as many parts as the cap needs -
panels_1.pdf, panels_2.pdf, ... - so splitting, not quality, is what keeps a
file under the cap. Only a panel too big to fit in a part on its own gives up
exactness: it takes the smallest of a no-dither palette (256 down to 16
colors) or 4:4:4 JPEG that still reaches a PSNR floor against its own
pixels, and a panel that can't fit even at the last floor stops the build.

Each part starts with a text page: the chapter's identity, reading direction,
which panels this part holds and the chapter's full panel list, and the story
so far (the previous chapter's memory section) when there is one.

Why not Pillow's own PDF writer: it re-encodes every image as JPEG, with no
way to turn that off (see writer.py)."""

from __future__ import annotations

import io
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from remanga.console import console, escape as _esc
from remanga.pdf.manifest_info import build_part_info, info_to_text_lines
from remanga.pdf.writer import (
    ImagePage,
    PngStream,
    build_pdf,
    decode_predictor2,
    encode_predictor2,
    png_idat_stream,
)

# The quality floors a page may step down through, best first, when its PDF
# would otherwise go over the cap - PSNR in dB against the page's own
# pixels. At 45 the difference is invisible side by side; 36 is the floor,
# below which a page is better off in a split PDF than degraded further.
PSNR_FLOORS = (45.0, 42.0, 39.0, 36.0)
_PALETTE_SIZES = (256, 128, 64, 32, 16)
_JPEG_QUALITIES = (95, 92, 88, 85, 80)

# Bytes each image page adds to a PDF around its stream (image, content and
# page objects plus their xref lines) - an estimate for packing parts; every
# part is measured exactly once it is built.
_PAGE_OVERHEAD = 600

_WORKERS = min(8, os.cpu_count() or 1)


def _load_array(path: Path) -> tuple[Image.Image, np.ndarray]:
    """The image as RGB or L, and its pixels. A page whose three channels are
    identical everywhere is returned as L - the same pixels exactly, a third
    of the data."""
    img = open_normalized(path)
    if img.mode == "RGBA":
        # PDF's DeviceRGB has no alpha.
        img = img.convert("RGB")
    arr = np.asarray(img)
    if arr.ndim == 3 and np.array_equal(arr[:, :, 0], arr[:, :, 1]) and np.array_equal(arr[:, :, 1], arr[:, :, 2]):
        img = img.convert("L")
        arr = np.asarray(img)
    return img, arr


def _psnr(original: np.ndarray, other: Image.Image, mode: str) -> float:
    back = np.asarray(other.convert(mode), dtype=np.float32)
    mse = float(np.mean((back - original.astype(np.float32)) ** 2))
    return float("inf") if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def _png_page(stream: PngStream, lossless: bool) -> ImagePage:
    return ImagePage(stream.width, stream.height, stream.data, colors=stream.colors, predictor=15,
                     palette=stream.palette, bits=stream.bits, lossless=lossless)


def _jpeg_passthrough(path: Path) -> ImagePage | None:
    """The file itself as a DCTDecode page, when it is a grayscale or RGB
    JPEG with no EXIF rotation (which a PDF reader would not apply)."""
    try:
        with Image.open(path) as img:
            if img.format != "JPEG" or img.mode not in ("L", "RGB"):
                return None
            if img.getexif().get(0x0112, 1) != 1:
                return None
            width, height, colors = img.width, img.height, 1 if img.mode == "L" else 3
    except OSError:
        return None
    return ImagePage(width, height, path.read_bytes(), colors=colors, predictor=None, filter="DCTDecode")


def _lossless_page(path: Path) -> ImagePage:
    """The smallest lossless PDF page for this image, verified before it is
    trusted: PNG's per-row filters (taken from a PNG Pillow wrote, which it
    must decode back to identical pixels) or TIFF Predictor 2 (decoded back
    here). Raises only if neither round-trips."""
    img, arr = _load_array(path)
    colors = 1 if arr.ndim == 2 else 3
    candidates: list[ImagePage] = []

    # A JPEG source goes in as its own bytes: the page then holds exactly the
    # file it came from, where re-encoding its decoded pixels losslessly would
    # be several times the size (a downloaded chapter's pages, typically).
    source = _jpeg_passthrough(path)
    if source is not None:
        candidates.append(source)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    png = buf.getvalue()
    if pixel_identical(img, png):
        stream = png_idat_stream(png)
        if (stream.width, stream.height, stream.colors, stream.palette) == (img.width, img.height, colors, None):
            candidates.append(_png_page(stream, lossless=True))

    shaped = arr if arr.ndim == 3 else arr[:, :, None]
    data = encode_predictor2(shaped)
    if np.array_equal(decode_predictor2(data, shaped.shape), shaped):
        candidates.append(ImagePage(img.width, img.height, data, colors=colors, predictor=2))

    if not candidates:
        raise ValueError(f"no lossless encoding round-tripped exactly for {path.name}")
    return min(candidates, key=lambda page: len(page.data))


def _near_lossless_pages(path: Path) -> list[tuple[ImagePage, float]]:
    """Every near-lossless page this image has, each with its PSNR against
    the original: palette versions (quantized without dithering, so line
    art stays crisp) and JPEG versions (no chroma subsampling). A candidate
    that fails to encode is left out."""
    img, arr = _load_array(path)
    out: list[tuple[ImagePage, float]] = []
    rgb = img.convert("RGB")
    for size in _PALETTE_SIZES:
        try:
            quantized = rgb.quantize(size, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            buf = io.BytesIO()
            quantized.save(buf, "PNG", optimize=True)
            out.append((_png_page(png_idat_stream(buf.getvalue()), lossless=False),
                        _psnr(arr, quantized, img.mode)))
        except (ValueError, OSError):
            continue
    colors = 1 if img.mode == "L" else 3
    for quality in _JPEG_QUALITIES:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, subsampling=0, optimize=True)
        data = buf.getvalue()
        with Image.open(io.BytesIO(data)) as decoded:
            psnr = _psnr(arr, decoded, img.mode)
        out.append((ImagePage(img.width, img.height, data, colors=colors, predictor=None,
                              filter="DCTDecode", lossless=False), psnr))
    return out


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
        for page, near in zip(todo, pool.map(lambda p: _near_lossless_pages(p.path), todo), strict=True):
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


def open_normalized(path: Path) -> Image.Image:
    """An image in RGB or RGBA mode, loaded."""
    img = Image.open(path)
    img.load()
    return img if img.mode in ("RGB", "RGBA") else img.convert("RGB")


def pixel_identical(reference: Image.Image, candidate_bytes: bytes) -> bool:
    """Whether `candidate_bytes` decodes back to exactly `reference`'s pixels."""
    try:
        with Image.open(io.BytesIO(candidate_bytes)) as decoded:
            decoded.load()
            if decoded.size != reference.size:
                return False
            if decoded.mode != reference.mode:
                decoded = decoded.convert(reference.mode)
            return decoded.tobytes() == reference.tobytes()
    except Exception:
        return False


def build_panels_pdf(
    image_paths: list[Path],
    out_dir: Path,
    max_mb: float,
    info: dict[str, Any],
) -> list[Path]:
    """Writes `out_dir`/panels_1.pdf, panels_2.pdf, ... from `image_paths`,
    each at most `max_mb`, replacing any parts from an earlier build. `info`
    is the chapter's identity and anything else the text page should carry.
    Returns the parts written; raises when a panel can't be encoded or can't
    fit under the cap."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("p*_*.pdf"):  # panels_*.pdf, and any pages_*.pdf from before
        stale.unlink()
    max_bytes = max(1, int(max_mb * 1024 * 1024))

    paths = list(image_paths)
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        lossless = list(pool.map(_lossless_page, paths))
    pages = [_Page(path.stem, path, page) for path, page in zip(paths, lossless, strict=True)]
    full_ids = [page.stem for page in pages]

    def render(part: Sequence[_Page], index: int, total: int) -> _Built:
        part_info = build_part_info(info, full_ids, [page.stem for page in part], index, total)
        return _Built(build_pdf([page.page for page in part], info_to_text_lines(part_info)))

    built = _pack_parts(pages, max_bytes, render)
    if built is None:
        raise ValueError(f"A panel is over the {max_mb:g}MB cap on its own, even at {PSNR_FLOORS[-1]:g} dB PSNR - "
                         f"raise the cap.")

    written = []
    for index, part in enumerate(built, start=1):
        path = out_dir / f"panels_{index}.pdf"
        path.write_bytes(part.pdf)
        written.append(path)
    total_mb = sum(p.stat().st_size for p in written) / (1024 * 1024)
    console.print(f"[bold green]✓ PDF of {len(pages)} panels - {len(written)} file(s), {total_mb:.1f}MB, each at most "
                  f"{max_mb:g}MB:[/] {_esc(str(out_dir))} [dim]({_quality_note(pages)})[/]")
    return written
