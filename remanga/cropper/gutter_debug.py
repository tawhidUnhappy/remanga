"""Standalone CLI for eyeballing the gutter-snap result on one panel of one page,
without running the full crop pipeline:

    python -m remanga.cropper.gutter_debug <page_image> <ymin> <xmin> <ymax> <xmax> [out_debug.png]

Coordinates are in the same normalized 0-1000 scale crops.json uses. Draws the
LLM's original box (red) and the gutter-refined box (green) over the page image
for a visual sanity check. Debug/manual-use only - never imported by the
production crop pipeline.
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw

from remanga.cropper.geometry import calculate_pixel_bounds
from remanga.cropper.gutter import (
    PixelBox,
    count_adjusted_edges,
    page_grayscale_array,
    refine_box_to_gutters,
    sample_background_color,
)


def _debug_visualize(page_path: str, box: PixelBox, refined: PixelBox, out_path: str) -> None:
    """Draws the LLM's original box (red) and the gutter-refined box (green) over
    the page for visual sanity-checking."""
    img = Image.open(page_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle(box, outline=(255, 0, 0), width=3)
    draw.rectangle(refined, outline=(0, 200, 0), width=3)
    img.save(out_path)


def main() -> None:
    if len(sys.argv) < 6:
        print(__doc__)
        raise SystemExit(1)

    page_path = sys.argv[1]
    ymin, xmin, ymax, xmax = (int(v) for v in sys.argv[2:6])
    out_path = sys.argv[6] if len(sys.argv) > 6 else "gutter_debug.png"

    img = Image.open(page_path)
    img_w, img_h = img.size
    gray = page_grayscale_array(img)
    bg = sample_background_color(gray)

    original_box = calculate_pixel_bounds([ymin, xmin, ymax, xmax], img_w, img_h, is_1000=True)
    refined_box = refine_box_to_gutters(gray, original_box, bg)

    print(f"Page background level (0-255): {bg:.1f}")
    print(f"LLM guess (pixels, L/T/R/B):     {original_box}")
    print(f"Gutter-refined (pixels, L/T/R/B): {refined_box}")
    print(f"Edges adjusted: {count_adjusted_edges(original_box, refined_box)}/4")

    _debug_visualize(page_path, original_box, refined_box, out_path)
    print(f"Debug overlay (red=LLM guess, green=refined) saved to: {out_path}")


if __name__ == "__main__":
    main()
