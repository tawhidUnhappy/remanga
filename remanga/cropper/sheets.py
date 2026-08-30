"""Consolidates sequential manga panels into labeled contact-sheet composites
for LLM vision upload (sheets.zip/sheets_zip - see remanga.cropper.archive
and remanga.cropper.llm_sheets).

Every panel is merged in at its full original resolution - the composite
canvas is sized from the panels' own native pixel dimensions, never the
other way around, so nothing here ever downscales a panel to fit a
pre-picked canvas size the way the previous fixed 1920x1080 layout did.
File size is kept in check purely by picking whichever verified-lossless
re-encoding of the (large) resulting composite comes out smallest -
remanga.cropper.image_codec.smallest_lossless_encoding_for_image, the exact
same quality-preserving guarantee every other vision bundle in this codebase
already makes for individual panels. "Original quality" here means exactly
that: every pixel a sheet ships is bit-identical to the source panel crop,
just chosen from whichever lossless container happens to hold it smallest."""

from __future__ import annotations

import math
from pathlib import Path
from typing import List
from PIL import Image, ImageDraw, ImageFont

from remanga.console import console
from remanga.cropper.image_codec import smallest_lossless_encoding_for_image


class PanelSheetGenerator:
    """Consolidates sequential manga panels into labeled contact sheets for LLM vision optimization."""

    # A label strip above each panel, not overlaid on it - the artwork
    # itself is never touched or covered.
    HEADER_HEIGHT = 32
    GAP = 6
    BG_COLOR = (18, 18, 18)
    HEADER_COLOR = (35, 35, 35)
    LABEL_COLOR = (0, 255, 200)

    @staticmethod
    def create_panel_sheets(
        panel_paths: List[Path],
        output_dir: Path,
        panels_per_sheet: int = 4,
    ) -> List[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Clear previous sheets (any extension from a previous run's chosen encoding)
        for old_file in output_dir.glob("sheet_*.*"):
            try:
                old_file.unlink()
            except Exception:
                pass

        if not panel_paths:
            return []

        gen = PanelSheetGenerator

        # Determine grid dimensions (2x2 for 4 panels, 2x3 for 6 panels, etc.)
        cols = 2 if panels_per_sheet <= 4 else 3
        rows = math.ceil(panels_per_sheet / cols)

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        generated_sheets: List[Path] = []
        total_sheets = math.ceil(len(panel_paths) / panels_per_sheet)

        console.print(
            f"[cyan]Generating {total_sheets} full-resolution vision contact sheet(s) "
            f"({panels_per_sheet} panels/sheet, losslessly re-encoded smaller)...[/]"
        )

        for sheet_idx in range(total_sheets):
            chunk = panel_paths[sheet_idx * panels_per_sheet: (sheet_idx + 1) * panels_per_sheet]

            # Load every panel in this sheet up front - their native sizes
            # decide the canvas layout below, nothing gets resized to fit a
            # pre-picked canvas the way a fixed-size sheet would.
            images = []
            for p_path in chunk:
                with Image.open(p_path) as src_img:
                    src_img.load()
                    images.append(src_img.convert("RGB") if src_img.mode != "RGB" else src_img.copy())

            col_widths = [0] * cols
            row_heights = [0] * rows
            for i, img in enumerate(images):
                r, c = divmod(i, cols)
                col_widths[c] = max(col_widths[c], img.width)
                row_heights[r] = max(row_heights[r], img.height)

            canvas_w = sum(col_widths) + gen.GAP * (cols + 1)
            canvas_h = sum(h + gen.HEADER_HEIGHT for h in row_heights) + gen.GAP * (rows + 1)
            sheet_canvas = Image.new("RGB", (canvas_w, canvas_h), color=gen.BG_COLOR)
            draw = ImageDraw.Draw(sheet_canvas)

            col_x = [gen.GAP]
            for w in col_widths[:-1]:
                col_x.append(col_x[-1] + w + gen.GAP)
            row_y = [gen.GAP]
            for h in row_heights[:-1]:
                row_y.append(row_y[-1] + h + gen.HEADER_HEIGHT + gen.GAP)

            for i, (p_path, img) in enumerate(zip(chunk, images)):
                r, c = divmod(i, cols)
                cell_x, cell_y, cell_w = col_x[c], row_y[r], col_widths[c]

                # Label header bar, sized to this column's actual width - not
                # a fixed cell size, since columns can differ in width now.
                panel_tag = f"[{p_path.stem}]"
                draw.rectangle(
                    [cell_x, cell_y, cell_x + cell_w, cell_y + gen.HEADER_HEIGHT - 4],
                    fill=gen.HEADER_COLOR,
                )
                draw.text((cell_x + 8, cell_y + 6), panel_tag, fill=gen.LABEL_COLOR, font=font)

                # Pasted at full native resolution, centered in its column if
                # narrower than the column's widest panel - never resized.
                paste_x = cell_x + (cell_w - img.width) // 2
                paste_y = cell_y + gen.HEADER_HEIGHT
                sheet_canvas.paste(img, (paste_x, paste_y))
                img.close()

            # Smallest verified-lossless container wins (PNG or lossless
            # WEBP) - same guarantee individual panel crops already get, see
            # module docstring. The extension is only known once this picks
            # a winner, so the sheet's final filename is decided here too.
            data, ext = smallest_lossless_encoding_for_image(sheet_canvas)
            sheet_path = output_dir / f"sheet_{sheet_idx + 1:03d}{ext}"
            sheet_path.write_bytes(data)
            generated_sheets.append(sheet_path)

        console.print(f"[bold green]✓ Created {len(generated_sheets)} full-resolution panel sheets in:[/] {output_dir}")
        return generated_sheets
