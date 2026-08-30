"""Builds the `sheets_folders` package format - the plain-folder alternative
to the composited grid sheets in remanga.cropper.sheets: instead of merging
several panels into one labeled contact-sheet image, this just copies each
panel crop, untouched and at full original resolution, into small numbered
subfolders of `panels_per_folder` panels each (default 10, configurable via
CropperConfig.panels_per_folder in config.json). Useful for upload
interfaces that accept a folder/multi-file drop but choke on either a single
giant contact-sheet image or a zip archive.

Written to sheets_folders/folder_001/, sheets_folders/folder_002/, ....
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import List

from remanga.console import console


class PanelFolderGenerator:
    """Groups panel crops into fixed-size numbered subfolders - no image
    compositing, no re-encoding, just organizing the existing files."""

    FOLDER_WIDTH = 3

    @staticmethod
    def create_panel_folders(
        panel_paths: List[Path],
        output_dir: Path,
        panels_per_folder: int = 10,
    ) -> List[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Full wipe first, same rule as sheets.py - a stray leftover folder
        # from a previous run (different group size, different panel count)
        # must never survive into the fresh set.
        for old in output_dir.iterdir():
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)
            elif old.is_file():
                try:
                    old.unlink()
                except Exception:
                    pass

        if not panel_paths:
            return []

        if panels_per_folder < 1:
            panels_per_folder = 1

        total_folders = math.ceil(len(panel_paths) / panels_per_folder)
        console.print(
            f"[cyan]Grouping {len(panel_paths)} panel(s) into {total_folders} folder(s) "
            f"({panels_per_folder} panels/folder)...[/]"
        )

        folder_paths: List[Path] = []
        for folder_idx in range(total_folders):
            chunk = panel_paths[folder_idx * panels_per_folder: (folder_idx + 1) * panels_per_folder]
            folder_name = f"folder_{str(folder_idx + 1).zfill(PanelFolderGenerator.FOLDER_WIDTH)}"
            folder_path = output_dir / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            for p_path in chunk:
                shutil.copy2(p_path, folder_path / p_path.name)
            folder_paths.append(folder_path)
            console.print(f"[dim]  ↳ {folder_name}: {len(chunk)} item(s)[/]")

        console.print(
            f"[bold green]✓ Grouped {len(panel_paths)} panels into {len(folder_paths)} folders "
            f"(total items: {len(panel_paths)}) in:[/] {output_dir}"
        )
        return folder_paths
