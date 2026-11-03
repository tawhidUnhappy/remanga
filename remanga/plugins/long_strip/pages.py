"""A run's marks packed into strip/ pages: tiles of the run top to bottom,
each holding whole marks, about a manga page's shape.

A page is cut only halfway across a gap no mark covers. Marks that touch or
overlap (a forced cut through a bubble, a bubble shared by two panels) always
land on one page: across two pages they could never be put right again."""

from __future__ import annotations

from itertools import pairwise

from remanga.plugins.long_strip.marks import MIN_MARK_ROWS, Mark

# Marks are packed onto a page until it would pass this height / width.
TARGET_ASPECT = 1.45


def run_marks(marks: list[Mark], top: int, height: int) -> list[Mark]:
    """The marks inside one run, in its own rows - a mark reaching into the
    next run (a cover of another width) is cut at the join."""
    out = []
    for m_top, m_bottom, left, right in marks:
        a, b = max(m_top, top) - top, min(m_bottom, top + height) - top
        if b - a >= MIN_MARK_ROWS:
            out.append((a, b, left, right))
    return out


def plan_pages(marks: list[Mark], height: int, width: int) -> list[tuple[int, int, list[Mark]]]:
    """(top, bottom, the page's marks in page rows) for every page of a run."""
    if not marks:
        return [(0, height, [])]
    groups: list[list[Mark]] = [[marks[0]]]
    reach = marks[0][1]                      # lowest row the current group covers
    for mark in marks[1:]:
        joined = mark[0] <= reach            # touches or overlaps what is there
        if not joined and mark[1] - groups[-1][0][0] > width * TARGET_ASPECT:
            groups.append([mark])
            reach = mark[1]
        else:
            groups[-1].append(mark)
            reach = max(reach, mark[1])
    bottoms = [max(m[1] for m in group) for group in groups]
    cuts = [0] + [(bottom + nxt[0][0]) // 2 for bottom, nxt in zip(bottoms, groups[1:], strict=False)] + [height]
    return [(top, bottom, [(a - top, b - top, left, right) for a, b, left, right in group])
            for (top, bottom), group in zip(pairwise(cuts), groups, strict=True)]
