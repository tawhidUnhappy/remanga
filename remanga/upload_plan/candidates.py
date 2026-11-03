"""The images an upload PDF offers for thumbnails: each chapter's largest cut
panels - where the artist put the weight of the chapter: the reveal, the
splash, the big reaction - and its colour pages (a cover is usually the only
colour art there is, and the heroine in colour sells a thumbnail).

A long manga has thousands of panels and a thumbnail needs two, so the
offer is capped: every chosen chapter gets the same share of MAX_CANDIDATES,
its largest panels, in reading order. A panel too small to fill half a
thumbnail sharply is never offered."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from remanga.narration import page_files, panel_files

MAX_CANDIDATES = 320
PER_CHAPTER = (6, 80)           # the least and most panels a chapter offers
MAX_COLOUR_PAGES = 24
MIN_SIDE, MIN_AREA = 250, 120_000   # pixels: anything smaller is soft at half a 1280x720 thumbnail
MIN_PAGE_SIDE = 600             # a colour "page" smaller than this is a scanlator's banner, not a page
IMAGE_MAX_SIDE = 1100           # the PDF's copy: plenty to judge a face by, and the LLM sees no more
JPEG_QUALITY = 85


@dataclass(frozen=True)
class Candidate:
    id: str                 # a panel id (001_014_02) or a page's name without its extension (001_002)
    kind: str               # panel | page
    chapter: str
    path: Path
    size: tuple[int, int]
    colour: bool

    def record(self) -> dict:
        return {"kind": self.kind, "chapter": self.chapter, "file": self.path.name, "size": list(self.size),
                "colour": self.colour}


def is_colour(path: Path) -> bool:
    """A colour image, not a black-and-white page with a scan's tint."""
    with Image.open(path) as image:
        small = image.convert("RGB")
        small.thumbnail((192, 192))
    saturation = np.asarray(small.convert("HSV"))[..., 1]
    return float(saturation.mean()) > 30 and float(np.percentile(saturation, 90)) > 80


def pick(project: str, chapters: list[str], not_story: set[str] = frozenset()) -> list[Candidate]:
    """What the chapters offer, in chapter and reading order - never a panel
    the narration skipped as not story (credits, an ad)."""
    quota = max(PER_CHAPTER[0], min(PER_CHAPTER[1], MAX_CANDIDATES // max(1, len(chapters))))
    offered: list[Candidate] = []
    colour_pages = 0
    for chapter in chapters:
        sized = []
        for path in panel_files(project, chapter):
            if path.stem in not_story:
                continue
            with Image.open(path) as image:
                size = image.size
            if min(size) >= MIN_SIDE and size[0] * size[1] >= MIN_AREA:
                sized.append((path, size))
        biggest = {p for p, s in sorted(sized, key=lambda ps: ps[1][0] * ps[1][1], reverse=True)[:quota]}
        story_pages = {p.stem.rsplit("_", 1)[0] for p in panel_files(project, chapter) if p.stem not in not_story}
        skipped_pages = {stem.rsplit("_", 1)[0] for stem in not_story} - story_pages
        for page in page_files(project, chapter):
            if colour_pages >= MAX_COLOUR_PAGES or page.stem in skipped_pages:
                continue
            with Image.open(page) as image:
                size = image.size
            whole = any(p.stem.rsplit("_", 1)[0] == page.stem and s[0] * s[1] >= 0.85 * size[0] * size[1]
                        for p, s in sized if p in biggest)   # its one panel is the page, offered as a panel
            if min(size) >= MIN_PAGE_SIDE and not whole and is_colour(page):
                offered.append(Candidate(page.stem, "page", chapter, page, size, True))
                colour_pages += 1
        offered += [Candidate(p.stem, "panel", chapter, p, s, is_colour(p)) for p, s in sized if p in biggest]
    return offered


def prepared(candidate: Candidate, out_dir: Path) -> Path:
    """The candidate as the PDF shows it: shrunk to IMAGE_MAX_SIDE, its id
    stamped at its foot - nothing added around it, so a box the LLM reads off
    it is in thousandths of the image itself."""
    with Image.open(candidate.path) as image:
        im = ImageOps.exif_transpose(image).convert("RGB")
    im.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(im, "RGBA")
    font = ImageFont.load_default(size=max(16, round(max(im.size) / 34)))
    stamp = candidate.id + ("  colour page" if candidate.kind == "page" else "")
    at = (im.width / 2, im.height - 8)
    box = d.textbbox(at, stamp, font=font, anchor="md")
    d.rectangle((box[0] - 8, box[1] - 5, box[2] + 8, box[3] + 5), fill=(0, 0, 0, 175))
    d.text(at, stamp, fill="white", font=font, anchor="md")
    path = out_dir / f"{candidate.id}.jpg"
    im.save(path, quality=JPEG_QUALITY)
    return path
