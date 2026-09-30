"""A long strip's panels, proposed by several methods voting together, as
[top, bottom) rows of one run:

1. gutters.py  - rows of one colour, trusted as gutters only once the strip
                 proves that colour separates panels (a flat sky never does);
2. borders.py  - borders with no gutter: a straight cut across the width, a
                 new picture starting, or two scenes' colours meeting
                 (signals.py fuses the three);
3. glued       - a small piece (a bubble, a sound effect floating between two
                 panels) joins the neighbour across the narrower gap;
4. blank       - a piece with no busy row (a plain fade, blank paper) is dropped;
5. quiet.py    - a picture taller than 1.8x the width is split at its calmest
                 stretch, never forced; one with none stays whole and is
                 reported as tall, for a look.

No fixed-point splitting: the method this replaced cut every tall block at
even intervals whatever was there, through faces and bubbles."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
from PIL import Image

from remanga.longstrip.borders import borders
from remanga.longstrip.gutters import Gutter, verified_gutters
from remanga.longstrip.quiet import TALL, split_tall
from remanga.longstrip.signals import measure

Range = tuple[int, int]

SMALL_SHARE = 0.45      # a piece shorter than this x the width is glued, not a panel
EDGE_MARGIN = 0.08      # a border this close (x width) to a gutter is that gutter's own edge
FEATURELESS = 4.0
PADDING = 2


@dataclass
class Detection:
    panels: list[Range] = field(default_factory=list)
    gutters: list[Gutter] = field(default_factory=list)
    borders: list[int] = field(default_factory=list)    # cuts found with no gutter
    tall: list[Range] = field(default_factory=list)     # panels left taller than TALL x width


def between_gutters(height: int, gutters: list[Gutter]) -> list[Range]:
    """The art between the gutters, padded a little into each."""
    edges = [0] + [y for g in gutters for y in (g.top, g.bottom)] + [height]
    out = []
    for top, bottom in zip(edges[::2], edges[1::2], strict=True):
        top, bottom = max(0, top - PADDING), min(height, bottom + PADDING)
        if bottom > top:
            out.append((top, bottom))
    return out


def cut_at(blocks: list[Range], cuts: list[int], margin: int) -> list[Range]:
    """Each block split at the borders inside it (not at its own edges)."""
    out = []
    for top, bottom in blocks:
        inner = [y for y in cuts if top + margin <= y <= bottom - margin]
        out += list(pairwise([top, *inner, bottom]))
    return out


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
    pieces = cut_at(between_gutters(height, gutters), found, int(EDGE_MARGIN * width))
    pieces = glue_small(pieces, width)
    pieces = [p for p in pieces if float(signals.busy[p[0]:p[1]].max(initial=0)) > FEATURELESS]
    panels = [part for top, bottom in pieces for part in split_tall(top, bottom, signals.energy, width)]
    tall = [p for p in panels if p[1] - p[0] > TALL * width]
    return Detection(panels, gutters, found, tall)
