"""Builds the panels_pdf package format - see remanga.cropper.llm_zip's
module docstring for the zip format this mirrors closely (same per-part
chapter identity, same PackageConfig.max_mb); this is the PDF equivalent for
chat interfaces that handle a single PDF upload more gracefully than a zip
of individual images. Off by default, unlike panels_zip.

Four independent switches (see PackageConfig), all coordinated here:
- `pdf` - a single panels_1.pdf, unsplit.
- `pdf_splite` - the PDF split into `max_mb`-capped raw .pdf files instead,
  not zipped: panels_1.pdf, panels_2.pdf, ....
- `pdf_zip` - the single PDF, wrapped in panels_1.zip.
- `pdf_zip_splite` - the PDF split into `max_mb`-capped parts, each zipped
  separately: panels_1.zip, panels_2.zip, ....

Written to panels_pdf/ - never touches panels/ itself.

The builder itself, `build_pdf_bundle`, takes those four switches as plain
arguments, so the LLM crop extension's grid_pdf formats (the same four
switches over gridded pages - see remanga.extensions.llm_crop.bundles)
are built by exactly this code too.

The size cap: no PDF file (and no zip holding one) is ever written above
`max_mb`, split or not - many chat interfaces refuse a bigger PDF outright.
Every page starts lossless, in the smallest of two verified lossless
encodings (see _lossless_page), and pure-grayscale pages are stored as one
channel instead of three. A JPEG source is embedded as its own bytes - the
source exactly, and far smaller than any re-encoding of its pixels. What happens when that doesn't fit:

- Split formats start a new part - more files, no quality touched. Only a
  page too big to fit in a part on its own gives up exactness, as below.
- Unsplit formats have one file, so pages give up exactness - biggest
  saving first, and only as far as the file needs. Each page then takes
  the smallest of a set of near-lossless encodings that still reaches a
  quality floor measured against its own pixels (PSNR_FLOORS): a palette
  of 256 down to 16 colors, which suits black-and-white art with a green
  grid (crisp lines, no ringing), or JPEG with no chroma subsampling, which
  suits color art. Every page reaches one floor before any page drops to
  the next, and none goes below the last. A chapter that still doesn't fit
  is not built, with a message saying so, rather than shipped oversized or
  degraded beyond that floor.

The console line says how many pages stayed lossless, and for any that
didn't, the lowest PSNR among them.

See remanga.cropper.pdf_writer's module docstring for why this doesn't just
use Pillow's own `Image.save(..., "PDF")` (short version: it re-encodes every
page as JPEG, with no way to turn that off short of quantizing to a
256-color palette).
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from remanga.config import CropperConfig
from remanga.console import console, escape as _esc
from remanga.cropper.image_codec import open_normalized, pixel_identical
from remanga.cropper.manifest_info import build_part_info, info_to_text_lines
from remanga.cropper.pdf_writer import (
    ImagePage,
    PngStream,
    build_pdf,
    decode_predictor2,
    encode_predictor2,
    png_idat_stream,
)
from remanga.paths import chapter_identity_fields, get_panels_pdf_dir

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
        # PDF's DeviceRGB has no alpha; every panel crop.py produces is RGB
        # already, so this only matters for some other file in the folder.
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
    zipped: bytes | None

    @property
    def size(self) -> int:
        return max(len(self.pdf), len(self.zipped or b""))


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


def _clear(out_dir: Path, file_prefix: str) -> None:
    for stale in out_dir.glob(f"{file_prefix}_*.pdf"):
        stale.unlink()
    for stale in out_dir.glob(f"{file_prefix}_*.zip"):
        stale.unlink()


def _quality_note(pages: Sequence[_Page]) -> str:
    changed = [page.choice(page.level)[1] for page in pages if not page.page.lossless]
    if not changed:
        return f"all {len(pages)} pages lossless"
    return (f"{len(pages) - len(changed)} pages lossless, {len(changed)} near-lossless to fit "
            f"(lowest PSNR {min(changed):.1f} dB)")


def build_pdf_bundle(
    image_paths: list[Path],
    out_dir: Path,
    file_prefix: str,
    single: bool,
    split: bool,
    zipped: bool,
    zipped_split: bool,
    max_mb: float,
    project_name: str,
    chapter_num: str,
    label: str,
    extra_info: dict[str, Any] | None = None,
) -> list[Path]:
    """Builds `out_dir`/`file_prefix`_1.pdf, _2.pdf, ... (and/or the zipped
    .zip parts) from `image_paths`, every file at most `max_mb` - see the
    module docstring for how. The four switches mean what PackageConfig's
    pdf/pdf_splite/pdf_zip/pdf_zip_splite mean. A no-op returning [] if none
    is on or there are no images. Clears out any stale parts from a previous
    run first. An image that can't be encoded, or a chapter that can't be
    fitted under the cap, aborts the whole bundle rather than shipping a PDF
    missing a page or over the cap. `extra_info` is added to every part's
    info (see manifest_info.build_part_info)."""
    if not (single or split or zipped or zipped_split) or not image_paths:
        if out_dir.exists():
            _clear(out_dir, file_prefix)
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    _clear(out_dir, file_prefix)
    max_bytes = max(1, int(max_mb * 1024 * 1024))

    paths = sorted(image_paths)
    try:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            lossless = list(pool.map(_lossless_page, paths))
    except Exception as e:
        console.print(f"[bold red]✗ LLM {label} bundle aborted:[/] a page couldn't be losslessly encoded ({e}) "
                      f"- the other upload formats are unaffected.")
        return []
    pages = [_Page(path.stem, path, page) for path, page in zip(paths, lossless, strict=True)]

    identity = chapter_identity_fields(project_name, chapter_num)
    full_ids = [page.stem for page in pages]
    write_pdf, write_zip = single or split, zipped or zipped_split

    def render(part: Sequence[_Page], index: int, total: int) -> _Built:
        info = build_part_info(identity, full_ids, [page.stem for page in part], index, total, extra=extra_info)
        pdf = build_pdf([page.page for page in part], info_to_text_lines(info))
        if not write_zip:
            return _Built(pdf, None)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # Stored, not deflated: every page stream is compressed already,
            # so deflating the PDF again only costs time.
            zf.writestr(f"{file_prefix}_{index}.pdf", pdf, compress_type=zipfile.ZIP_STORED)
            zf.writestr("chapter_info.json", json.dumps(info, indent=2) + "\n",
                        compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        return _Built(pdf, buf.getvalue())

    split_parts = split or zipped_split
    if split_parts:
        built = _pack_parts(pages, max_bytes, render)
    else:
        one = _fit_one_file(pages, max_bytes, render, 1, 1)
        built = [one] if one is not None else None
    if built is None:
        how = (f"a page is over the cap on its own, even at {PSNR_FLOORS[-1]:g} dB PSNR" if split_parts else
               f"not even with every page at {PSNR_FLOORS[-1]:g} dB PSNR - pick a split PDF format, or raise the cap")
        console.print(f"[bold red]✗ LLM {label} bundle not built:[/] it can't fit in {max_mb:g}MB per file ({how}). "
                      f"The other upload formats are unaffected.")
        return []

    written: list[Path] = []
    for index, part in enumerate(built, start=1):
        if write_pdf:
            pdf_path = out_dir / f"{file_prefix}_{index}.pdf"
            pdf_path.write_bytes(part.pdf)
            written.append(pdf_path)
        if write_zip:
            zip_path = out_dir / f"{file_prefix}_{index}.zip"
            zip_path.write_bytes(part.zipped)
            written.append(zip_path)

    total_mb = sum(p.stat().st_size for p in written) / (1024 * 1024)
    largest_mb = max(p.stat().st_size for p in written) / (1024 * 1024)
    parts_note = f"{len(built)} part(s)" if split_parts else "1 file"
    console.print(
        f"[bold green]✓ Built LLM upload bundle - {label} ({parts_note}, largest {largest_mb:.1f}MB of "
        f"{max_mb:g}MB allowed, {total_mb:.1f}MB total) in:[/] {_esc(str(out_dir))} [dim]({_quality_note(pages)})[/]"
    )
    return written


def build_llm_pdf_bundle(
    config: CropperConfig,
    project_name: str,
    chapter_num: str,
    panel_paths: list[Path],
) -> list[Path]:
    """Builds panels_pdf/panels_1.pdf, panels_2.pdf, ... - see module
    docstring."""
    package = config.package
    return build_pdf_bundle(
        panel_paths, get_panels_pdf_dir(project_name, chapter_num, create=False), "panels",
        package.pdf, package.pdf_splite, package.pdf_zip, package.pdf_zip_splite, package.max_mb,
        project_name, chapter_num, "PDF",
    )
