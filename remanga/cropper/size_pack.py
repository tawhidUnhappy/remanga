"""Generic greedy bin-packing by byte size - shared by the zip bundle
(llm_zip.py) and the PDF bundle (llm_pdf.py) to split a chapter's panels into
as many size-capped parts as needed, in original order, splitting only on
panel boundaries."""

from __future__ import annotations

from typing import Callable, List, Sequence, TypeVar

T = TypeVar("T")


def pack_by_size(items: Sequence[T], size_of: Callable[[T], int], max_bytes: int) -> List[List[T]]:
    """Greedily fills each part up to `max_bytes`, in the given order. A new
    part only starts once the current one is non-empty AND the next item
    wouldn't fit, so a single item bigger than `max_bytes` on its own still
    gets a (solo, oversized) part instead of being split or dropped.
    `size_of(item)` computes each item's own byte contribution to a part."""
    if not items:
        return []

    parts: List[List[T]] = [[]]
    part_sizes = [0]
    for item in items:
        size = size_of(item)
        if part_sizes[-1] > 0 and part_sizes[-1] + size > max_bytes:
            parts.append([])
            part_sizes.append(0)
        parts[-1].append(item)
        part_sizes[-1] += size
    return parts
