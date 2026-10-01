"""Borders between panels that have no gutter: the rows where the fused
border score (signals.py) peaks above BORDER_SCORE. A peak must stand alone -
a textured stretch (hatching, rain, a crowd) scores high on many rows in a
row, a border on one or two - and borders closer than MIN_GAP rows keep only
the stronger."""

from __future__ import annotations

import numpy as np

from remanga.plugins.long_strip.signals import RowSignals, border_score

BORDER_SCORE = 0.5
MIN_GAP = 40            # rows between two borders
CALM_AROUND = 0.35      # the score a few rows away must fall under this


def borders(s: RowSignals) -> list[int]:
    score = border_score(s)
    picked: list[int] = []
    for y in np.flatnonzero(score >= BORDER_SCORE):
        around = np.concatenate((score[max(0, y - 6):max(0, y - 2)], score[y + 3:y + 7]))
        if around.size and around.max() >= CALM_AROUND:
            continue
        if picked and y - picked[-1] < MIN_GAP:
            if score[y] > score[picked[-1]]:
                picked[-1] = int(y)
            continue
        picked.append(int(y))
    return picked
