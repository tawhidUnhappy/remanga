"""Per-row measurements of a strip that the panel detector votes with.

Each one answers "does a new panel start at this row?" from a different
angle, so a border one of them misses another sees:

    edge    the share of the width that changes sharply from the row above -
            a panel border is a straight cut across the whole width, where a
            line inside a picture wobbles and stops;
    decor   how unlike the row above this one is (1 - correlation of the two
            grey profiles) - a new picture starting, even under a soft border;
    band    how different the colours of the rows just above and just below
            are - two panels of different scenes meeting with no line at all;
    energy  how busy the rows around here are (rolling max of each row's grey
            spread) - low only in a genuinely calm stretch (a background),
            which is where a tall picture may be split without cutting
            through a face or a bubble.

Measured on a real chapter against the user's own marks: at the borders with
no gutter that any signal can see, edge reached 0.72-0.99 where the
99th percentile inside panels is 0.15, and band 0.39-0.59 against 0.25."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

EDGE_JUMP = 40          # grey-level change that counts as sharp
BAND_ROWS = 16          # rows compared either side for `band`
ENERGY_HALF_BAND = 30   # rows either side a calm stretch has to hold for


@dataclass
class RowSignals:
    edge: np.ndarray
    decor: np.ndarray
    band: np.ndarray
    energy: np.ndarray
    busy: np.ndarray    # each row's own grey spread (0 = one flat tone)


def measure(arr: np.ndarray) -> RowSignals:
    """All four signals for an RGB strip (height x width x 3). Every other
    column is enough and halves the work."""
    rgb = arr[:, ::2, :].astype(np.int16)
    gray = rgb.mean(axis=2, dtype=np.float32)
    h = rgb.shape[0]

    edge = np.zeros(h, dtype=np.float32)
    edge[1:] = (np.abs(rgb[1:] - rgb[:-1]).max(axis=2) > EDGE_JUMP).mean(axis=1)

    centred = gray - gray.mean(axis=1, keepdims=True)
    norm = np.sqrt((centred * centred).sum(axis=1)) + 1e-3
    decor = np.zeros(h, dtype=np.float32)
    decor[1:] = 1 - (centred[1:] * centred[:-1]).sum(axis=1) / (norm[1:] * norm[:-1])
    busy = gray.std(axis=1)
    flat = busy < 4
    decor[flat | np.roll(flat, 1)] = 0          # a flat row correlates with nothing; that is no border

    k = BAND_ROWS
    sums = np.cumsum(np.vstack([np.zeros((1, rgb.shape[1], 3), np.float32), rgb.astype(np.float32)]), axis=0)
    band = np.zeros(h, dtype=np.float32)
    ys = np.arange(k, h - k)
    if ys.size:
        band[ys] = np.abs((sums[ys] - sums[ys - k]) - (sums[ys + k] - sums[ys])).mean(axis=(1, 2)) / (k * 255)

    padded = np.pad(busy, ENERGY_HALF_BAND, mode="edge")
    energy = np.lib.stride_tricks.sliding_window_view(padded, 2 * ENERGY_HALF_BAND + 1).max(axis=1)
    return RowSignals(edge, decor, band, energy, busy)


def border_score(s: RowSignals) -> np.ndarray:
    """The three border signals fused into one 0..1 score per row."""
    return 0.5 * s.edge + 0.3 * np.minimum(1, 2 * s.band) + 0.2 * np.minimum(1, 2 * s.decor)
