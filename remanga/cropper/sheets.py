from __future__ import annotations

import math
from pathlib import Path
from typing import List
from PIL import Image, ImageDraw, ImageFont

from remanga.console import console


class PanelSheetGenerator:
    """Consolidates sequential manga panels into labeled contact sheets for LLM vision optimization."""

    @staticmethod
    def create_panel_sheets(
        panel_paths: List[Path],
        output_dir: Path,
        panels_per_sheet: int = 4,
        sheet_width: int = 1920,
        sheet_height: int = 1080,
    ) -> List[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Clear previous sheets
        for old_file in output_dir.glob("sheet_*.*"):
            try:
                old_file.unlink()
            except Exception:
                pass

        if not panel_paths:
            return []

        # Determine grid dimensions (2x2 for 4 panels, 2x3 for 6 panels, etc.)
        cols = 2 if panels_per_sheet <= 4 else 3
        rows = math.ceil(panels_per_sheet / cols)

        cell_w = sheet_width // cols
        cell_h = sheet_height // rows
        header_height = 42

        generated_sheets: List[Path] = []
        total_sheets = math.ceil(len(panel_paths) / panels_per_sheet)

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        console.print(f"[cyan]Generating {total_sheets} vision-optimized panel sheet(s) ({panels_per_sheet} panels/sheet)...[/]")

        for sheet_idx in range(total_sheets):
            sheet_canvas = Image.new("RGB", (sheet_width, sheet_height), color=(18, 18, 18))
            draw = ImageDraw.Draw(sheet_canvas)

            chunk = panel_paths[sheet_idx * panels_per_sheet : (sheet_idx + 1) * panels_per_sheet]

            for i, p_path in enumerate(chunk):
                r = i // cols
                c = i % cols

                cell_x = c * cell_w
                cell_y = r * cell_h

                # Draw cell bounding border
                draw.rectangle(
                    [cell_x + 4, cell_y + 4, cell_x + cell_w - 4, cell_y + cell_h - 4],
                    outline=(60, 60, 60),
                    width=2,
                )

                # Draw panel label header bar
                panel_tag = f"[{p_path.stem}]"
                draw.rectangle(
                    [cell_x + 6, cell_y + 6, cell_x + cell_w - 6, cell_y + header_height],
                    fill=(35, 35, 35),
                )
                draw.text(
                    (cell_x + 16, cell_y + 12),
                    panel_tag,
                    fill=(0, 255, 200),
                    font=font,
                )

                # Load and fit panel image into remaining cell area
                usable_w = cell_w - 20
                usable_h = cell_h - header_height - 20

                with Image.open(p_path) as p_img:
                    p_img = p_img.convert("RGB")
                    pw, ph = p_img.size

                    scale = min(usable_w / pw, usable_h / ph)
                    fit_w = max(1, int(pw * scale))
                    fit_h = max(1, int(ph * scale))

                    resized_p = p_img.resize((fit_w, fit_h), Image.Resampling.LANCZOS)

                    paste_x = cell_x + (cell_w - fit_w) // 2
                    paste_y = cell_y + header_height + (usable_h - fit_h) // 2

                    sheet_canvas.paste(resized_p, (paste_x, paste_y))

            sheet_path = output_dir / f"sheet_{sheet_idx + 1:03d}.png"
            sheet_canvas.save(sheet_path, "PNG", optimize=True)
            generated_sheets.append(sheet_path)

        console.print(f"[bold green]✓ Created {len(generated_sheets)} panel sheets in:[/] {output_dir}")
        return generated_sheets