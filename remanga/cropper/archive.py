"""Packages cropped panel/sheet assets into the chapter's vision-upload zip archive."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from rich.console import Console

from remanga.config import CropperConfig

console = Console()


def create_vision_archive(
    config: CropperConfig, chapter_dir: Path, panels_dir: Path, sheets_dir: Optional[Path]
) -> Path:
    """Packages cropped assets into either sheets.zip (2x2 contact sheets) or
    panels.zip (individual crops) based on the user's configured vision_asset_type."""
    asset_type = getattr(config, "vision_asset_type", "sheets").lower()
    zip_filename = config.expected_zip_name
    zip_path = chapter_dir / zip_filename

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if asset_type == "sheets":
            if sheets_dir and sheets_dir.exists() and list(sheets_dir.glob("sheet_*.*")):
                for s in sorted(list(sheets_dir.glob("sheet_*.*"))):
                    zf.write(s, arcname=s.name)
            else:
                for p in sorted(list(panels_dir.glob("panel_*.*"))):
                    zf.write(p, arcname=p.name)
        else:
            for p in sorted(list(panels_dir.glob("panel_*.*"))):
                zf.write(p, arcname=p.name)

        manifest = chapter_dir / "panels_manifest.json"
        if manifest.exists():
            zf.write(manifest, arcname="panels_manifest.json")

    console.print(f"[bold green]✓ Created Vision Archive ({zip_filename} - Mode: {asset_type.upper()}):[/] {zip_path}")
    return zip_path
