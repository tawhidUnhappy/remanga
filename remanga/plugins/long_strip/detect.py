"""A long strip's panels, proposed by several methods together, as
[top, bottom) rows of one run:

1. gutters.py  - rows of one colour, trusted as gutters only once the strip
                 proves that colour separates panels (a flat sky never does);
                 the art between them is the first cut;
2. glued       - a small piece (a bubble, a sound effect floating between two
                 panels) joins the neighbour across the narrower gap;
3. blank       - a piece with no busy row (a plain fade, blank paper) is dropped;
4. quiet.py    - a picture taller than 1.8x the width is split - at a strong
                 border (borders.py: a straight cut across the width, a new
                 picture starting, two scenes' colours meeting) if there is
                 one in its middle part, else at its calmest stretch, never
                 forced; one with neither stays whole and is reported as tall,
                 for a look.

Borders never cut a picture on their own. Measured against the user's marks
on three chapters (253 panels), about 140 rows passed the border vote, and
only 3 were cuts the user kept: a straight line inside a picture - a horizon,
a fence, a desk, a caption box's edge - looks just like a cut to it, and
those false cuts were the complaint (2026-10-19). Kept only as split points
of a too-tall picture, they still find the user's cuts they found before,
with a third fewer false ones.

No fixed-point splitting: the method this replaced cut every tall block at
even intervals whatever was there, through faces and bubbles."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
from PIL import Image

from remanga.plugins.long_strip.borders import borders
from remanga.plugins.long_strip.gutters import Gutter, verified_gutters
from remanga.plugins.long_strip.quiet import TALL, split_tall
from remanga.plugins.long_strip.signals import border_score, measure

Range = tuple[int, int]

SMALL_SHARE = 0.45      # a piece shorter than this x the width is glued, not a panel
STRONG_BORDER = 0.6     # fused border score a border needs to split a tall picture
# A piece whose busiest row has less grey spread than this is blank (a fade,
# paper, JPEG noise on white): every panel the user marked on three chapters
# has a row over 36, a soft white fade between two gutters 6.
FEATURELESS = 15.0
PADDING = 2


@dataclass
class Detection:
    panels: list[Range] = field(default_factory=list)
    gutters: list[Gutter] = field(default_factory=list)
    borders: list[int] = field(default_factory=list)    # borders found with no gutter
    tall: list[Range] = field(default_factory=list)     # panels left taller than TALL x width


def between_gutters(height: int, gutters: list[Gutter]) -> list[Range]:
    """The art between the gutters, padded a little into each - none between
    two gutters that touch (the steps of a fade)."""
    edges = [0] + [y for g in gutters for y in (g.top, g.bottom)] + [height]
    return [(max(0, top - PADDING), min(height, bottom + PADDING))
            for top, bottom in zip(edges[::2], edges[1::2], strict=True) if bottom > top]


def glue_small(pieces: list[Range], width: int) -> list[Range]:
    """Small pieces joined to the neighbour across the narrower gap."""
    if len(pieces) < 2:
        return pieces
    small = [b - t < width * SMALL_SHARE for t, b in pieces]
    gaps = [nxt[0] - prev[1] for prev, nxt in pairwise(pieces)]    # gaps[i] is below piece i
    join = [False] * len(gaps)
    for i, is_small in enumerate(small):
        if not is_small:
            continue
        above = gaps[i - 1] if i > 0 else None
        below = gaps[i] if i < len(gaps) else None
        if below is not None and (above is None or below < above):
            join[i] = True
        elif above is not None:
            join[i - 1] = True
    out = [list(pieces[0])]
    for piece, joined in zip(pieces[1:], join, strict=True):
        if joined:
            out[-1][1] = piece[1]
        else:
            out.append(list(piece))
    return [(t, b) for t, b in out]


def detect(image: Image.Image) -> Detection:
    """One run's panels, and what was found on the way, in the run's own rows."""
    arr = np.asarray(image.convert("RGB"))
    height, width = arr.shape[:2]
    signals = measure(arr)
    gutters = verified_gutters(arr)
    found = borders(signals)
    score = border_score(signals)
    strong = [(y, float(score[y])) for y in found if score[y] >= STRONG_BORDER]
    pieces = glue_small(between_gutters(height, gutters), width)
    pieces = [p for p in pieces if float(signals.busy[p[0]:p[1]].max(initial=0)) > FEATURELESS]
    panels = [part for top, bottom in pieces for part in split_tall(top, bottom, signals.energy, width, strong)]
    tall = [p for p in panels if p[1] - p[0] > TALL * width]
    return Detection(panels, gutters, found, tall)
